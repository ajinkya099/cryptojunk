"""Certification campaign API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from iga.database import get_db
from iga.models.policy import CertificationDecision
from iga.services.certification import CertificationService

router = APIRouter()


class CampaignCreate(BaseModel):
    name: str
    scope_applications: list[str] | None = None
    scope_roles: list[str] | None = None
    scope_departments: list[str] | None = None
    duration_days: int | None = None
    owner_id: str | None = None


class CertificationDecisionRequest(BaseModel):
    decision: CertificationDecision
    certifier_id: str
    reason: str | None = None


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_campaign(
    request: CampaignCreate, db: AsyncSession = Depends(get_db)
) -> dict:
    service = CertificationService(db)
    campaign = await service.create_campaign(
        name=request.name,
        scope_applications=request.scope_applications,
        scope_roles=request.scope_roles,
        scope_departments=request.scope_departments,
        duration_days=request.duration_days,
        owner_id=request.owner_id,
    )
    return {
        "campaign_id": campaign.id,
        "name": campaign.name,
        "status": campaign.status,
        "message": "Campaign created. Use /launch to activate and generate items.",
    }


@router.post("/{campaign_id}/launch")
async def launch_campaign(
    campaign_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    service = CertificationService(db)
    campaign = await service.launch_campaign(campaign_id)
    if not campaign:
        raise HTTPException(
            status_code=404,
            detail="Campaign not found or not in DRAFT status",
        )
    return {
        "campaign_id": campaign.id,
        "status": campaign.status,
        "total_items": campaign.total_items,
        "end_date": campaign.end_date.isoformat() if campaign.end_date else None,
    }


@router.get("/{campaign_id}/progress")
async def get_campaign_progress(
    campaign_id: str, db: AsyncSession = Depends(get_db)
) -> dict:
    service = CertificationService(db)
    progress = await service.get_campaign_progress(campaign_id)
    if not progress:
        raise HTTPException(status_code=404, detail="Campaign not found")
    return progress


@router.post("/items/{item_id}/decide")
async def submit_decision(
    item_id: str,
    request: CertificationDecisionRequest,
    db: AsyncSession = Depends(get_db),
) -> dict:
    service = CertificationService(db)
    item = await service.submit_decision(
        item_id=item_id,
        decision=request.decision,
        certifier_id=request.certifier_id,
        reason=request.reason,
    )
    if not item:
        raise HTTPException(
            status_code=404,
            detail="Item not found or already decided",
        )
    return {
        "item_id": item.id,
        "decision": item.decision,
        "decided_at": item.decided_at.isoformat() if item.decided_at else None,
    }
