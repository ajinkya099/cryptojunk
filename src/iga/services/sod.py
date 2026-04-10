"""SoD service — Segregation of Duties policy management."""

from __future__ import annotations

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.models.policy import SoDPolicy, SoDViolation, SoDViolationSeverity, SoDViolationStatus


class SoDService:
    """Business logic for SoD policy and violation management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_policy(
        self,
        name: str,
        description: str | None,
        severity: SoDViolationSeverity,
        side_a_roles: list[str],
        side_b_roles: list[str],
        remediation_guidance: str | None = None,
        owner_id: str | None = None,
    ) -> SoDPolicy:
        policy = SoDPolicy(
            name=name,
            description=description,
            severity=severity,
            side_a_roles=side_a_roles,
            side_b_roles=side_b_roles,
            remediation_guidance=remediation_guidance,
            owner_id=owner_id,
            is_active=True,
        )
        self.session.add(policy)
        await self.session.flush()
        return policy

    async def get_open_violations(
        self,
        identity_id: str | None = None,
        severity: SoDViolationSeverity | None = None,
        limit: int = 100,
    ) -> list[SoDViolation]:
        stmt = select(SoDViolation).where(
            SoDViolation.status == SoDViolationStatus.OPEN
        )
        if identity_id:
            stmt = stmt.where(SoDViolation.identity_id == identity_id)
        if severity:
            # Join policy to filter by severity
            stmt = stmt.join(SoDPolicy).where(SoDPolicy.severity == severity)
        stmt = stmt.order_by(SoDViolation.detected_at.desc()).limit(limit)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def accept_risk(
        self,
        violation_id: str,
        accepted_by: str,
        reason: str,
    ) -> SoDViolation | None:
        stmt = select(SoDViolation).where(SoDViolation.id == violation_id)
        row = await self.session.execute(stmt)
        violation = row.scalar_one_or_none()

        if not violation:
            return None

        violation.status = SoDViolationStatus.ACCEPTED
        violation.resolved_by = accepted_by
        violation.resolution_notes = reason
        from datetime import datetime
        violation.resolved_at = datetime.utcnow()
        return violation

    async def get_policy_summary(self) -> list[dict]:
        """Return a summary of all SoD policies and their violation counts."""
        policies = await self.session.execute(select(SoDPolicy))
        result = []
        for policy in policies.scalars():
            violations = await self.session.execute(
                select(SoDViolation).where(
                    SoDViolation.policy_id == policy.id,
                    SoDViolation.status == SoDViolationStatus.OPEN,
                )
            )
            open_count = len(list(violations.scalars()))
            result.append(
                {
                    "policy_id": policy.id,
                    "name": policy.name,
                    "severity": policy.severity,
                    "is_active": policy.is_active,
                    "open_violations": open_count,
                }
            )
        return result
