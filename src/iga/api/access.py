"""Access request API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.database import get_db
from iga.models.access import AccessRequest, AccessRequestStatus

router = APIRouter()


class AccessRequestCreate(BaseModel):
    requester_id: str
    beneficiary_id: str
    role_id: str | None = None
    permission_id: str | None = None
    application_id: str | None = None
    business_justification: str | None = None
    requested_duration_days: int | None = None


@router.get("")
async def list_access_requests(
    status: AccessRequestStatus | None = None,
    beneficiary_id: str | None = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    stmt = select(AccessRequest)
    if status:
        stmt = stmt.where(AccessRequest.status == status)
    if beneficiary_id:
        stmt = stmt.where(AccessRequest.beneficiary_id == beneficiary_id)
    stmt = stmt.order_by(AccessRequest.created_at.desc()).limit(limit)
    rows = await db.execute(stmt)
    requests = rows.scalars().all()
    return [
        {
            "id": r.id,
            "requester_id": r.requester_id,
            "beneficiary_id": r.beneficiary_id,
            "role_id": r.role_id,
            "permission_id": r.permission_id,
            "status": r.status,
            "ai_recommendation": r.ai_recommendation,
            "ai_risk_score": r.ai_risk_score,
            "created_at": r.created_at.isoformat(),
        }
        for r in requests
    ]


@router.post("", status_code=201)
async def create_access_request(
    request: AccessRequestCreate, db: AsyncSession = Depends(get_db)
) -> dict:
    """Create a new access request — AI risk assessment runs asynchronously."""
    ar = AccessRequest(
        requester_id=request.requester_id,
        beneficiary_id=request.beneficiary_id,
        role_id=request.role_id,
        permission_id=request.permission_id,
        application_id=request.application_id,
        business_justification=request.business_justification,
        requested_duration_days=request.requested_duration_days,
        status=AccessRequestStatus.PENDING_APPROVAL,
    )
    db.add(ar)
    await db.flush()
    # AI risk assessment is triggered asynchronously via Celery
    return {
        "request_id": ar.id,
        "status": ar.status,
        "message": "Access request submitted. AI risk assessment queued.",
    }


@router.get("/{request_id}")
async def get_access_request(
    request_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    stmt = select(AccessRequest).where(AccessRequest.id == request_id)
    row = await db.execute(stmt)
    ar = row.scalar_one_or_none()
    if not ar:
        raise HTTPException(status_code=404, detail="Access request not found")
    return {
        "id": ar.id,
        "requester_id": ar.requester_id,
        "beneficiary_id": ar.beneficiary_id,
        "role_id": ar.role_id,
        "status": ar.status,
        "business_justification": ar.business_justification,
        "ai_recommendation": ar.ai_recommendation,
        "ai_risk_score": ar.ai_risk_score,
        "ai_reasoning": ar.ai_reasoning,
        "ai_sod_conflicts": ar.ai_sod_conflicts,
        "created_at": ar.created_at.isoformat(),
    }
