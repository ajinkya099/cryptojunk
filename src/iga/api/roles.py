"""Role management API routes."""

from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from iga.database import get_db
from iga.models.role import RoleStatus, RoleType
from iga.services.role_management import RoleManagementService

router = APIRouter()


class RoleCreate(BaseModel):
    name: str
    display_name: str
    role_type: RoleType = RoleType.BUSINESS
    description: str | None = None
    risk_score: int = 1
    owner_id: str | None = None
    requires_approval: bool = True
    requires_certification: bool = True


class RoleAssignRequest(BaseModel):
    identity_id: str
    role_id: str
    assigned_by: str
    reason: str | None = None


class RoleRevokeRequest(BaseModel):
    identity_id: str
    role_id: str
    revoked_by: str
    reason: str | None = None


@router.get("")
async def list_roles(
    role_type: RoleType | None = None,
    db: AsyncSession = Depends(get_db),
) -> list[dict]:
    service = RoleManagementService(db)
    roles = await service.get_all_roles(role_type=role_type)
    return [
        {
            "id": r.id,
            "name": r.name,
            "display_name": r.display_name,
            "role_type": r.role_type,
            "risk_score": r.risk_score,
            "status": r.status,
            "requires_approval": r.requires_approval,
        }
        for r in roles
    ]


@router.post("", status_code=status.HTTP_201_CREATED)
async def create_role(
    request: RoleCreate, db: AsyncSession = Depends(get_db)
) -> dict:
    service = RoleManagementService(db)
    role = await service.create_role(
        name=request.name,
        display_name=request.display_name,
        role_type=request.role_type,
        description=request.description,
        risk_score=request.risk_score,
        owner_id=request.owner_id,
        requires_approval=request.requires_approval,
        requires_certification=request.requires_certification,
    )
    return {"id": role.id, "name": role.name, "status": role.status}


@router.post("/assign", status_code=status.HTTP_201_CREATED)
async def assign_role(
    request: RoleAssignRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    service = RoleManagementService(db)
    assignment = await service.assign_role(
        identity_id=request.identity_id,
        role_id=request.role_id,
        assigned_by=request.assigned_by,
        reason=request.reason,
    )
    return {
        "assignment_id": assignment.id,
        "identity_id": assignment.identity_id,
        "role_id": assignment.role_id,
        "is_active": assignment.is_active,
    }


@router.post("/revoke")
async def revoke_role(
    request: RoleRevokeRequest, db: AsyncSession = Depends(get_db)
) -> dict:
    service = RoleManagementService(db)
    assignment = await service.revoke_role(
        identity_id=request.identity_id,
        role_id=request.role_id,
        revoked_by=request.revoked_by,
        reason=request.reason,
    )
    if not assignment:
        raise HTTPException(status_code=404, detail="Active role assignment not found")
    return {
        "assignment_id": assignment.id,
        "is_active": assignment.is_active,
        "revoked_at": assignment.revoked_at.isoformat() if assignment.revoked_at else None,
    }


@router.get("/{identity_id}/roles")
async def get_identity_roles(
    identity_id: str, db: AsyncSession = Depends(get_db)
) -> list[dict]:
    service = RoleManagementService(db)
    roles = await service.get_identity_roles(identity_id)
    return [
        {
            "id": r.id,
            "name": r.name,
            "display_name": r.display_name,
            "role_type": r.role_type,
            "risk_score": r.risk_score,
        }
        for r in roles
    ]
