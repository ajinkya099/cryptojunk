"""RoleMinerAgent — AI-driven role discovery and role engineering."""

from __future__ import annotations

import structlog
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.agents.base import AgentDecision, AgentResult, BaseAgent
from iga.database import AsyncSessionLocal
from iga.models.role import Role, RoleAssignment, RoleStatus, RoleType

logger = structlog.get_logger(__name__)

ROLE_MINER_SYSTEM_PROMPT = """
You are the RoleMinerAgent for an Identity Governance & Administration (IGA) system.
Your job is to analyze access patterns and discover or optimize roles.

Role Mining is the process of discovering natural groupings of permissions/access
that appear repeatedly across users, then formalizing these as roles.

Your tasks:
1. ROLE DISCOVERY: Identify groups of users with identical or near-identical access
   that don't yet have a formal role assigned
2. ROLE OPTIMIZATION: Identify existing roles that are too broad, too narrow,
   or rarely used
3. ROLE RECOMMENDATIONS: Suggest new roles based on job title + department patterns

Good roles have:
- Clear business meaning (not just technical groupings)
- A specific audience (job function + department)
- Consistent membership (>80% of users in the target group have it)
- Appropriate scope (not too broad — avoid "superuser" roles)

Problematic patterns to flag:
- Roles assigned to <3 users (might be too specific — use direct access instead)
- Roles assigned to >80% of all users (might be too broad)
- Users with >20 roles (role explosion — consider consolidation)
- Roles that overlap by >90% in permissions (consider merging)
"""


class RoleMinerAgent(BaseAgent):
    """
    Autonomous agent for role discovery and role engineering.

    - Runs weekly (Sunday nights) via Celery Beat
    - Analyzes access patterns across all identities
    - Discovers new role candidates
    - Suggests role optimizations
    - AI-generates role descriptions and risk scores
    """

    def __init__(self) -> None:
        super().__init__(
            name="role_miner",
            description="Discovers and optimizes roles from access patterns",
        )

    async def run(self) -> AgentResult:
        start_time = self._start_run()
        result = AgentResult(agent_name=self.name, success=True, dry_run=self.dry_run)

        async with AsyncSessionLocal() as session:
            try:
                # Analyze existing roles
                role_stats = await self._collect_role_statistics(session)
                result.items_processed = len(role_stats)

                self.log.info("role_mining_analysis", role_count=len(role_stats))

                # Ask AI to analyze and make recommendations
                for stat in role_stats:
                    decision = await self._analyze_role(stat)
                    result.decisions.append(decision)

                    if decision.action != "no_action":
                        result.items_actioned += 1
                        await self._apply_role_decision(session, stat, decision)

                # Generate new role candidates
                new_roles = await self._discover_new_roles(session)
                result.items_processed += len(new_roles)

                await session.commit()

            except Exception as e:
                result.success = False
                result.errors.append(str(e))
                self.log.error("role_miner_error", error=str(e))
                await session.rollback()

        return self._end_run(result, start_time)

    async def _collect_role_statistics(self, session: AsyncSession) -> list[dict]:
        """Collect usage statistics for all active roles."""
        stmt = (
            select(
                Role.id,
                Role.name,
                Role.display_name,
                Role.role_type,
                Role.risk_score,
                Role.description,
                func.count(RoleAssignment.id).label("assignment_count"),
            )
            .outerjoin(
                RoleAssignment,
                (RoleAssignment.role_id == Role.id) & (RoleAssignment.is_active == True),  # noqa: E712
            )
            .where(Role.status == RoleStatus.ACTIVE)
            .group_by(Role.id)
        )
        rows = await session.execute(stmt)
        return [
            {
                "role_id": row.id,
                "role_name": row.name,
                "display_name": row.display_name,
                "role_type": row.role_type,
                "risk_score": row.risk_score,
                "description": row.description,
                "assignment_count": row.assignment_count,
            }
            for row in rows
        ]

    async def _analyze_role(self, stat: dict) -> AgentDecision:
        return await self.make_decision(
            system_prompt=ROLE_MINER_SYSTEM_PROMPT,
            context={
                "role_analysis_task": "evaluate_existing_role",
                "role_data": stat,
            },
            decision_schema=(
                '{"action": "keep|deprecate|merge_candidate|split_candidate|update_description|no_action", '
                '"reasoning": "string", "confidence": 0.0-1.0, '
                '"requires_human_review": bool, "risk_level": "low|medium|high|critical", '
                '"data": {"suggested_description": "string", "suggested_risk_score": 1-10, '
                '"merge_with_role_id": null, "notes": "string"}}'
            ),
        )

    async def _apply_role_decision(
        self, session: AsyncSession, stat: dict, decision: AgentDecision
    ) -> None:
        if self.dry_run or not decision.is_high_confidence():
            self._log_decision(decision, context_id=stat["role_id"])
            return

        stmt = select(Role).where(Role.id == stat["role_id"])
        row = await session.execute(stmt)
        role = row.scalar_one_or_none()
        if not role:
            return

        data = decision.data
        if decision.action == "deprecate":
            role.status = RoleStatus.DEPRECATED
            self.log.info("role_deprecated", role_id=role.id, reason=decision.reasoning)
        elif decision.action == "update_description" and data.get("suggested_description"):
            role.ai_description = data["suggested_description"]
            if data.get("suggested_risk_score"):
                role.risk_score = data["suggested_risk_score"]
            role.ai_risk_reasoning = decision.reasoning

        self._log_decision(decision, context_id=stat["role_id"])

    async def _discover_new_roles(self, session: AsyncSession) -> list[dict]:
        """
        Discover potential new roles by analyzing access pattern clusters.
        Returns candidate role definitions for AI review.
        """
        # Simplified: get departments with many direct assignments (no role)
        # In production, use ML clustering on access vectors
        stmt = (
            select(
                RoleAssignment.identity_id,
                func.count(RoleAssignment.role_id).label("role_count"),
            )
            .where(RoleAssignment.is_active == True)  # noqa: E712
            .group_by(RoleAssignment.identity_id)
            .having(func.count(RoleAssignment.role_id) > 10)
            .limit(20)
        )
        rows = await session.execute(stmt)
        candidates = [
            {"identity_id": row.identity_id, "role_count": row.role_count}
            for row in rows
        ]

        if candidates:
            self.log.info(
                "role_discovery_candidates",
                count=len(candidates),
                note="Users with >10 roles are candidates for role consolidation",
            )

        return candidates
