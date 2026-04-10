"""Identity API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel, EmailStr
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.database import get_db
from iga.models.identity import Identity, IdentityStatus
from iga.services.lifecycle import LifecycleService

router = APIRouter()


class IdentityCreate(BaseModel):
    email: str
    display_name: str
    first_name: str | None = None
    last_name: str | None = None
    employee_id: str | None = None
    department: str | None = None
    job_title: str | None = None
    location: str | None = None
    cost_center: str | None = None
    hire_date: str | None = None


class JoinerRequest(BaseModel):
    identity: IdentityCreate
    triggered_by: str = "api"


class MoverRequest(BaseModel):
    identity_id: str
    new_department: str | None = None
    new_job_title: str | None = None
    new_manager_id: str | None = None
    triggered_by: str = "api"


class LeaverRequest(BaseModel):
    identity_id: str
    termination_date: str | None = None
    reason: str | None = None
    triggered_by: str = "api"


@router.get("")
async def list_identities(
    status: IdentityStatus | None = None,
    department: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(Identity)
    if status:
        stmt = stmt.where(Identity.status == status)
    if department:
        stmt = stmt.where(Identity.department == department)
    stmt = stmt.limit(limit)
    rows = await db.execute(stmt)
    identities = rows.scalars().all()
    return [
        {
            "id": i.id,
            "email": i.email,
            "display_name": i.display_name,
            "department": i.department,
            "job_title": i.job_title,
            "status": i.status,
            "is_privileged": i.is_privileged,
        }
        for i in identities
    ]


@router.get("/{identity_id}")
async def get_identity(
    identity_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    stmt = select(Identity).where(Identity.id == identity_id)
    row = await db.execute(stmt)
    identity = row.scalar_one_or_none()
    if not identity:
        raise HTTPException(status_code=404, detail="Identity not found")
    return {
        "id": identity.id,
        "email": identity.email,
        "display_name": identity.display_name,
        "first_name": identity.first_name,
        "last_name": identity.last_name,
        "employee_id": identity.employee_id,
        "department": identity.department,
        "job_title": identity.job_title,
        "manager_id": identity.manager_id,
        "status": identity.status,
        "is_privileged": identity.is_privileged,
        "is_service_account": identity.is_service_account,
        "hire_date": identity.hire_date.isoformat() if identity.hire_date else None,
        "termination_date": identity.termination_date.isoformat() if identity.termination_date else None,
        "created_at": identity.created_at.isoformat(),
    }


@router.post("/joiner", status_code=status.HTTP_201_CREATED)
async def trigger_joiner(
    request: JoinerRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Trigger a Joiner (new hire) lifecycle event — picked up by LifecycleAgent."""
    service = LifecycleService(db)
    event = await service.create_joiner_event(
        identity_data=request.identity.model_dump(),
        triggered_by=request.triggered_by,
    )
    return {"event_id": event.id, "status": event.status, "type": event.event_type}


@router.post("/mover", status_code=status.HTTP_201_CREATED)
async def trigger_mover(
    request: MoverRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Trigger a Mover (role/department change) lifecycle event."""
    service = LifecycleService(db)
    event = await service.create_mover_event(
        identity_id=request.identity_id,
        change_data=request.model_dump(),
        triggered_by=request.triggered_by,
    )
    return {"event_id": event.id, "status": event.status, "type": event.event_type}


@router.post("/leaver", status_code=status.HTTP_201_CREATED)
async def trigger_leaver(
    request: LeaverRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    """Trigger a Leaver (termination) lifecycle event."""
    service = LifecycleService(db)
    event = await service.create_leaver_event(
        identity_id=request.identity_id,
        termination_data=request.model_dump(),
        triggered_by=request.triggered_by,
    )
    return {"event_id": event.id, "status": event.status, "type": event.event_type}


@router.get("/{identity_id}/lifecycle-events")
async def get_lifecycle_events(
    identity_id: str, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    """Get all lifecycle events for an identity."""
    service = LifecycleService(db)
    events = await service.get_events_for_identity(identity_id)
    return [
        {
            "id": e.id,
            "event_type": e.event_type,
            "status": e.status,
            "triggered_by": e.triggered_by,
            "ai_decision": e.ai_decision,
            "ai_confidence": e.ai_confidence,
            "created_at": e.created_at.isoformat(),
            "processed_at": e.processed_at.isoformat() if e.processed_at else None,
        }
        for e in events
    ]
