"""Role management service — RBAC/ABAC operations."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.models.role import (
    Permission,
    Role,
    RoleAssignment,
    RolePermission,
    RoleStatus,
    RoleType,
)


class RoleManagementService:
    """Business logic for role lifecycle and assignment management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_role(
        self,
        name: str,
        display_name: str,
        role_type: RoleType = RoleType.BUSINESS,
        description: str | None = None,
        risk_score: int = 1,
        owner_id: str | None = None,
        requires_approval: bool = True,
        requires_certification: bool = True,
    ) -> Role:
        role = Role(
            name=name,
            display_name=display_name,
            role_type=role_type,
            description=description,
            risk_score=risk_score,
            owner_id=owner_id,
            requires_approval=requires_approval,
            requires_certification=requires_certification,
            status=RoleStatus.ACTIVE,
        )
        self.session.add(role)
        await self.session.flush()
        return role

    async def assign_role(
        self,
        identity_id: str,
        role_id: str,
        assigned_by: str,
        reason: str | None = None,
        expires_at: datetime | None = None,
        ai_reasoning: str | None = None,
        ai_confidence: float | None = None,
    ) -> RoleAssignment:
        # Check for existing active assignment
        stmt = select(RoleAssignment).where(
            RoleAssignment.identity_id == identity_id,
            RoleAssignment.role_id == role_id,
            RoleAssignment.is_active == True,  # noqa: E712
        )
        row = await self.session.execute(stmt)
        existing = row.scalar_one_or_none()
        if existing:
            return existing  # Already assigned

        assignment = RoleAssignment(
            identity_id=identity_id,
            role_id=role_id,
            assigned_by=assigned_by,
            assignment_reason=reason,
            expires_at=expires_at,
            is_active=True,
            ai_reasoning=ai_reasoning,
            ai_confidence=ai_confidence,
        )
        self.session.add(assignment)
        await self.session.flush()
        return assignment

    async def revoke_role(
        self,
        identity_id: str,
        role_id: str,
        revoked_by: str,
        reason: str | None = None,
    ) -> RoleAssignment | None:
        stmt = select(RoleAssignment).where(
            RoleAssignment.identity_id == identity_id,
            RoleAssignment.role_id == role_id,
            RoleAssignment.is_active == True,  # noqa: E712
        )
        row = await self.session.execute(stmt)
        assignment = row.scalar_one_or_none()
        if not assignment:
            return None

        assignment.is_active = False
        assignment.revoked_at = datetime.utcnow()
        assignment.revocation_reason = f"Revoked by {revoked_by}: {reason or 'no reason given'}"
        return assignment

    async def get_identity_roles(self, identity_id: str) -> list[Role]:
        stmt = (
            select(Role)
            .join(RoleAssignment, RoleAssignment.role_id == Role.id)
            .where(
                RoleAssignment.identity_id == identity_id,
                RoleAssignment.is_active == True,  # noqa: E712
            )
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def add_permission_to_role(
        self, role_id: str, permission_id: str
    ) -> RolePermission:
        rp = RolePermission(role_id=role_id, permission_id=permission_id)
        self.session.add(rp)
        await self.session.flush()
        return rp

    async def get_all_roles(
        self,
        role_type: RoleType | None = None,
        status: RoleStatus = RoleStatus.ACTIVE,
    ) -> list[Role]:
        stmt = select(Role).where(Role.status == status)
        if role_type:
            stmt = stmt.where(Role.role_type == role_type)
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())
