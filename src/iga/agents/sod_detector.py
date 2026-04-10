"""SoDDetectorAgent — Segregation of Duties violation detection and remediation."""

from __future__ import annotations

from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.agents.base import AgentDecision, AgentResult, BaseAgent
from iga.database import AsyncSessionLocal
from iga.models.identity import Identity, IdentityStatus
from iga.models.policy import SoDPolicy, SoDViolation, SoDViolationStatus
from iga.models.role import RoleAssignment

logger = structlog.get_logger(__name__)

SOD_SYSTEM_PROMPT = """
You are the SoDDetectorAgent for an Identity Governance & Administration (IGA) system.
Your job is to analyze potential Segregation of Duties (SoD) violations.

SoD violations occur when a single person has access to two or more conflicting
capabilities that together could enable fraud, error, or security compromise.

Classic examples:
- A person who can both CREATE purchase orders AND APPROVE them
- A person who can both INITIATE payments AND RECONCILE accounts
- A person who can both WRITE code AND DEPLOY to production
- A person who has both READ access to a database AND WRITE/DELETE access

For each potential violation, assess:
1. Is this a genuine SoD conflict or a false positive?
2. What is the actual risk? (consider: job role, department, actual usage)
3. What is the recommended remediation?
4. Is this urgent (e.g. financial fraud risk) or low risk (theoretical)?

Remediation options:
- "revoke_side_a": Remove the first set of conflicting access
- "revoke_side_b": Remove the second set of conflicting access
- "accept_risk": The conflict is low risk / justified by business need
- "escalate_to_manager": Need manager input on which access to revoke
- "immediate_revoke_all": Critical risk — revoke all conflicting access now

Be conservative: financial systems and privileged access conflicts are ALWAYS high risk.
"""


class SoDDetectorAgent(BaseAgent):
    """
    Autonomous agent for detecting and remediating SoD violations.

    - Runs every 30 minutes via Celery Beat
    - Scans all active identities against all active SoD policies
    - Creates SoDViolation records for new violations
    - Makes AI-driven remediation recommendations
    - Auto-remediates if configured and confidence is high
    """

    def __init__(self) -> None:
        super().__init__(
            name="sod_detector",
            description="Detects and remediates Segregation of Duties violations",
        )

    async def run(self) -> AgentResult:
        start_time = self._start_run()
        result = AgentResult(agent_name=self.name, success=True, dry_run=self.dry_run)

        async with AsyncSessionLocal() as session:
            try:
                policies = await self._fetch_active_policies(session)
                identities = await self._fetch_active_identities(session)

                self.log.info(
                    "sod_scan_starting",
                    policies=len(policies),
                    identities=len(identities),
                )

                for identity in identities:
                    role_ids = await self._get_identity_role_ids(session, identity.id)
                    if not role_ids:
                        continue

                    for policy in policies:
                        violation = await self._check_violation(
                            session, identity, policy, role_ids
                        )
                        result.items_processed += 1

                        if violation:
                            decision = await self._analyze_violation(violation, identity, policy)
                            result.decisions.append(decision)
                            result.items_actioned += 1
                            await self._handle_violation(session, violation, decision)

                await session.commit()

            except Exception as e:
                result.success = False
                result.errors.append(str(e))
                self.log.error("sod_detector_error", error=str(e))
                await session.rollback()

        return self._end_run(result, start_time)

    async def _fetch_active_policies(self, session: AsyncSession) -> list[SoDPolicy]:
        stmt = select(SoDPolicy).where(SoDPolicy.is_active == True)  # noqa: E712
        rows = await session.execute(stmt)
        return list(rows.scalars().all())

    async def _fetch_active_identities(self, session: AsyncSession) -> list[Identity]:
        stmt = (
            select(Identity)
            .where(Identity.status == IdentityStatus.ACTIVE)
            .limit(500)  # Batch processing
        )
        rows = await session.execute(stmt)
        return list(rows.scalars().all())

    async def _get_identity_role_ids(
        self, session: AsyncSession, identity_id: str
    ) -> list[str]:
        stmt = select(RoleAssignment.role_id).where(
            RoleAssignment.identity_id == identity_id,
            RoleAssignment.is_active == True,  # noqa: E712
        )
        rows = await session.execute(stmt)
        return list(rows.scalars().all())

    async def _check_violation(
        self,
        session: AsyncSession,
        identity: Identity,
        policy: SoDPolicy,
        role_ids: list[str],
    ) -> SoDViolation | None:
        """Check if an identity violates a specific SoD policy."""
        side_a = set(policy.side_a_roles or [])
        side_b = set(policy.side_b_roles or [])
        identity_roles = set(role_ids)

        has_side_a = bool(side_a & identity_roles)
        has_side_b = bool(side_b & identity_roles)

        if not (has_side_a and has_side_b):
            return None  # No conflict

        # Check if violation already exists
        stmt = select(SoDViolation).where(
            SoDViolation.policy_id == policy.id,
            SoDViolation.identity_id == identity.id,
            SoDViolation.status == SoDViolationStatus.OPEN,
        )
        existing = await session.execute(stmt)
        if existing.scalar_one_or_none():
            return None  # Already tracked

        # Create new violation record
        conflicting_a = list(side_a & identity_roles)
        conflicting_b = list(side_b & identity_roles)

        violation = SoDViolation(
            policy_id=policy.id,
            identity_id=identity.id,
            conflicting_role_ids=conflicting_a + conflicting_b,
            status=SoDViolationStatus.OPEN,
        )
        session.add(violation)
        await session.flush()  # Get the ID

        self.log.warning(
            "sod_violation_detected",
            identity_id=identity.id,
            policy=policy.name,
            conflicting_a=conflicting_a,
            conflicting_b=conflicting_b,
        )

        return violation

    async def _analyze_violation(
        self,
        violation: SoDViolation,
        identity: Identity,
        policy: SoDPolicy,
    ) -> AgentDecision:
        context = {
            "violation_id": violation.id,
            "policy_name": policy.name,
            "policy_severity": policy.severity,
            "policy_description": policy.description,
            "identity_id": identity.id,
            "identity_email": identity.email,
            "identity_department": identity.department,
            "identity_job_title": identity.job_title,
            "identity_is_privileged": identity.is_privileged,
            "conflicting_role_ids": violation.conflicting_role_ids,
            "remediation_guidance": policy.remediation_guidance,
            "auto_remediate": policy.auto_remediate,
        }

        return await self.make_decision(
            system_prompt=SOD_SYSTEM_PROMPT,
            context=context,
            decision_schema=(
                '{"action": "revoke_side_a|revoke_side_b|accept_risk|escalate_to_manager|immediate_revoke_all", '
                '"reasoning": "string", "confidence": 0.0-1.0, '
                '"requires_human_review": bool, "risk_level": "low|medium|high|critical", '
                '"data": {"recommended_revocation_targets": [], "business_impact": "string"}}'
            ),
        )

    async def _handle_violation(
        self,
        session: AsyncSession,
        violation: SoDViolation,
        decision: AgentDecision,
    ) -> None:
        violation.ai_risk_assessment = decision.reasoning
        violation.ai_recommended_action = decision.action
        violation.ai_confidence = decision.confidence

        self._log_decision(decision, context_id=violation.id)

        if self.dry_run:
            return

        # Auto-remediate if configured and high confidence
        if (
            decision.action in ("revoke_side_a", "revoke_side_b", "immediate_revoke_all")
            and decision.is_high_confidence()
            and decision.risk_level in ("high", "critical")
        ):
            # TODO: Call provisioning service to revoke conflicting access
            violation.status = SoDViolationStatus.REMEDIATED
            violation.resolved_at = datetime.utcnow()
            violation.resolved_by = "ai_agent:sod_detector"
            self.log.info(
                "sod_auto_remediated",
                violation_id=violation.id,
                action=decision.action,
            )
