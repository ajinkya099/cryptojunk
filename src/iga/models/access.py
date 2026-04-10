"""Access models: AccessAssignment, AccessRequest."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iga.database import Base


class AccessRequestStatus(str, Enum):
    DRAFT = "draft"
    PENDING_APPROVAL = "pending_approval"
    APPROVED = "approved"
    REJECTED = "rejected"
    PROVISIONED = "provisioned"
    REVOKED = "revoked"
    EXPIRED = "expired"
    CANCELLED = "cancelled"


class AccessAssignment(Base):
    """A direct access assignment (role or permission) for an identity."""

    __tablename__ = "access_assignments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identities.id"), index=True
    )
    # Either role or permission (not both)
    role_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("roles.id"), index=True
    )
    permission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("permissions.id"), index=True
    )
    application_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("applications.id"), index=True
    )

    # Assignment status
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    source: Mapped[str] = mapped_column(String(50), default="manual")  # manual | role | ai_agent
    granted_by: Mapped[str | None] = mapped_column(String(100))

    # Temporal controls
    granted_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    revocation_reason: Mapped[str | None] = mapped_column(Text)

    # Certification tracking
    last_certified_at: Mapped[datetime | None] = mapped_column(DateTime)
    last_certified_by: Mapped[str | None] = mapped_column(String(100))
    certification_due_at: Mapped[datetime | None] = mapped_column(DateTime)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    identity: Mapped["Identity"] = relationship(  # type: ignore[name-defined]
        back_populates="access_assignments",
        foreign_keys=[identity_id],
    )

    def __repr__(self) -> str:
        target = self.role_id or self.permission_id
        return f"<AccessAssignment identity={self.identity_id} target={target}>"


class AccessRequest(Base):
    """A request for access (role or permission) raised by or for an identity."""

    __tablename__ = "access_requests"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    requester_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identities.id"), index=True
    )
    beneficiary_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identities.id"), index=True
    )

    # What is being requested
    role_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("roles.id"))
    permission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("permissions.id")
    )
    application_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("applications.id")
    )

    status: Mapped[AccessRequestStatus] = mapped_column(
        String(30), default=AccessRequestStatus.PENDING_APPROVAL
    )

    # Request details
    business_justification: Mapped[str | None] = mapped_column(Text)
    requested_duration_days: Mapped[int | None] = mapped_column()

    # Approval chain
    approver_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("identities.id"))
    approved_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejected_at: Mapped[datetime | None] = mapped_column(DateTime)
    rejection_reason: Mapped[str | None] = mapped_column(Text)

    # AI risk assessment
    ai_risk_score: Mapped[float | None] = mapped_column()
    ai_recommendation: Mapped[str | None] = mapped_column(String(20))  # approve | reject | escalate
    ai_reasoning: Mapped[str | None] = mapped_column(Text)
    ai_sod_conflicts: Mapped[list | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    def __repr__(self) -> str:
        return f"<AccessRequest {self.id} [{self.status}]>"
