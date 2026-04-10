"""Lifecycle service — business logic for JML event management."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.models.identity import Identity, IdentityStatus, LifecycleEvent, LifecycleEventType, LifecycleEventStatus


class LifecycleService:
    """Business logic for identity lifecycle management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_joiner_event(
        self,
        identity_data: dict,
        triggered_by: str = "hr_system",
    ) -> LifecycleEvent:
        """Create a new joiner event for a new hire."""
        # Create or update identity
        identity = await self._get_or_create_identity(identity_data)

        event = LifecycleEvent(
            identity_id=identity.id,
            event_type=LifecycleEventType.JOINER,
            status=LifecycleEventStatus.PENDING,
            triggered_by=triggered_by,
            payload=identity_data,
            scheduled_at=datetime.utcnow(),
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def create_mover_event(
        self,
        identity_id: str,
        change_data: dict,
        triggered_by: str = "hr_system",
    ) -> LifecycleEvent:
        """Create a mover event for a role/department change."""
        event = LifecycleEvent(
            identity_id=identity_id,
            event_type=LifecycleEventType.MOVER,
            status=LifecycleEventStatus.PENDING,
            triggered_by=triggered_by,
            payload=change_data,
            scheduled_at=datetime.utcnow(),
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def create_leaver_event(
        self,
        identity_id: str,
        termination_data: dict,
        triggered_by: str = "hr_system",
    ) -> LifecycleEvent:
        """Create a leaver event for an employee departure."""
        # Mark identity as inactive immediately
        stmt = select(Identity).where(Identity.id == identity_id)
        row = await self.session.execute(stmt)
        identity = row.scalar_one_or_none()
        if identity:
            identity.status = IdentityStatus.INACTIVE
            identity.termination_date = termination_data.get(
                "termination_date", datetime.utcnow()
            )

        event = LifecycleEvent(
            identity_id=identity_id,
            event_type=LifecycleEventType.LEAVER,
            status=LifecycleEventStatus.PENDING,
            triggered_by=triggered_by,
            payload=termination_data,
            scheduled_at=datetime.utcnow(),
        )
        self.session.add(event)
        await self.session.flush()
        return event

    async def get_pending_events(self, limit: int = 50) -> list[LifecycleEvent]:
        stmt = (
            select(LifecycleEvent)
            .where(LifecycleEvent.status == LifecycleEventStatus.PENDING)
            .order_by(LifecycleEvent.created_at)
            .limit(limit)
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def get_events_for_identity(
        self, identity_id: str
    ) -> list[LifecycleEvent]:
        stmt = (
            select(LifecycleEvent)
            .where(LifecycleEvent.identity_id == identity_id)
            .order_by(LifecycleEvent.created_at.desc())
        )
        rows = await self.session.execute(stmt)
        return list(rows.scalars().all())

    async def _get_or_create_identity(self, data: dict) -> Identity:
        email = data.get("email", "")
        stmt = select(Identity).where(Identity.email == email)
        row = await self.session.execute(stmt)
        identity = row.scalar_one_or_none()

        if not identity:
            identity = Identity(
                email=email,
                display_name=data.get("display_name", email),
                first_name=data.get("first_name"),
                last_name=data.get("last_name"),
                employee_id=data.get("employee_id"),
                department=data.get("department"),
                job_title=data.get("job_title"),
                location=data.get("location"),
                cost_center=data.get("cost_center"),
                hire_date=data.get("hire_date"),
                status=IdentityStatus.PENDING,
            )
            self.session.add(identity)
            await self.session.flush()

        return identity
