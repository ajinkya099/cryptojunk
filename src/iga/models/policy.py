"""Policy models: SoDPolicy, SoDViolation, CertificationCampaign, CertificationItem."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iga.database import Base


class SoDViolationSeverity(str, Enum):
    LOW = "low"
    MEDIUM = "medium"
    HIGH = "high"
    CRITICAL = "critical"


class SoDViolationStatus(str, Enum):
    OPEN = "open"
    REMEDIATED = "remediated"
    ACCEPTED = "accepted"      # Risk accepted with justification
    FALSE_POSITIVE = "false_positive"
    IN_REVIEW = "in_review"


class CampaignStatus(str, Enum):
    DRAFT = "draft"
    ACTIVE = "active"
    COMPLETED = "completed"
    CANCELLED = "cancelled"


class CertificationDecision(str, Enum):
    PENDING = "pending"
    CERTIFIED = "certified"     # Access confirmed / kept
    REVOKED = "revoked"         # Access revoked
    REASSIGNED = "reassigned"   # Certifier changed
    AUTO_CERTIFIED = "auto_certified"   # AI auto-certified (high confidence)
    AUTO_REVOKED = "auto_revoked"       # AI auto-revoked (high confidence)


class SoDPolicy(Base):
    """A Segregation of Duties policy defining conflicting role/permission pairs."""

    __tablename__ = "sod_policies"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    description: Mapped[str | None] = mapped_column(Text)
    severity: Mapped[SoDViolationSeverity] = mapped_column(
        String(10), default=SoDViolationSeverity.HIGH
    )
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)

    # Conflicting sides (JSON arrays of role_ids or permission_ids)
    side_a_roles: Mapped[list | None] = mapped_column(JSON)
    side_a_permissions: Mapped[list | None] = mapped_column(JSON)
    side_b_roles: Mapped[list | None] = mapped_column(JSON)
    side_b_permissions: Mapped[list | None] = mapped_column(JSON)

    # Remediation guidance
    remediation_guidance: Mapped[str | None] = mapped_column(Text)
    auto_remediate: Mapped[bool] = mapped_column(Boolean, default=False)

    # AI-generated policy
    ai_generated: Mapped[bool] = mapped_column(Boolean, default=False)
    ai_reasoning: Mapped[str | None] = mapped_column(Text)

    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("identities.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    violations: Mapped[list["SoDViolation"]] = relationship(back_populates="policy")

    def __repr__(self) -> str:
        return f"<SoDPolicy {self.name} [{self.severity}]>"


class SoDViolation(Base):
    """A detected SoD policy violation for an identity."""

    __tablename__ = "sod_violations"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    policy_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("sod_policies.id"), index=True
    )
    identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identities.id"), index=True
    )
    status: Mapped[SoDViolationStatus] = mapped_column(
        String(20), default=SoDViolationStatus.OPEN
    )

    # What triggered it
    conflicting_role_ids: Mapped[list | None] = mapped_column(JSON)
    conflicting_permission_ids: Mapped[list | None] = mapped_column(JSON)

    # AI analysis
    ai_risk_assessment: Mapped[str | None] = mapped_column(Text)
    ai_recommended_action: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[float | None] = mapped_column()

    # Resolution
    resolved_by: Mapped[str | None] = mapped_column(String(100))
    resolution_notes: Mapped[str | None] = mapped_column(Text)
    detected_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    resolved_at: Mapped[datetime | None] = mapped_column(DateTime)

    # Relationships
    policy: Mapped["SoDPolicy"] = relationship(back_populates="violations")

    def __repr__(self) -> str:
        return f"<SoDViolation policy={self.policy_id} identity={self.identity_id} [{self.status}]>"


class CertificationCampaign(Base):
    """An access certification / access review campaign."""

    __tablename__ = "certification_campaigns"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    description: Mapped[str | None] = mapped_column(Text)
    status: Mapped[CampaignStatus] = mapped_column(String(20), default=CampaignStatus.DRAFT)

    # Scope
    scope_applications: Mapped[list | None] = mapped_column(JSON)  # application IDs
    scope_roles: Mapped[list | None] = mapped_column(JSON)          # role IDs
    scope_departments: Mapped[list | None] = mapped_column(JSON)    # departments

    # Timeline
    start_date: Mapped[datetime | None] = mapped_column(DateTime)
    end_date: Mapped[datetime | None] = mapped_column(DateTime)
    duration_days: Mapped[int] = mapped_column(default=14)

    # AI configuration
    ai_assist_enabled: Mapped[bool] = mapped_column(Boolean, default=True)
    auto_certify_threshold: Mapped[float] = mapped_column(default=0.95)
    auto_revoke_threshold: Mapped[float] = mapped_column(default=0.80)

    # Statistics
    total_items: Mapped[int] = mapped_column(default=0)
    certified_count: Mapped[int] = mapped_column(default=0)
    revoked_count: Mapped[int] = mapped_column(default=0)
    pending_count: Mapped[int] = mapped_column(default=0)
    ai_decided_count: Mapped[int] = mapped_column(default=0)

    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("identities.id"))
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    items: Mapped[list["CertificationItem"]] = relationship(back_populates="campaign")

    def __repr__(self) -> str:
        return f"<CertificationCampaign {self.name} [{self.status}]>"


class CertificationItem(Base):
    """An individual access item within a certification campaign."""

    __tablename__ = "certification_items"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    campaign_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("certification_campaigns.id"), index=True
    )
    identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identities.id"), index=True
    )
    certifier_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("identities.id"), index=True
    )

    # What is being certified
    access_assignment_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("access_assignments.id")
    )
    role_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("roles.id"))
    permission_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("permissions.id")
    )
    application_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("applications.id")
    )

    # Decision
    decision: Mapped[CertificationDecision] = mapped_column(
        String(30), default=CertificationDecision.PENDING
    )
    decision_reason: Mapped[str | None] = mapped_column(Text)
    decided_at: Mapped[datetime | None] = mapped_column(DateTime)

    # AI recommendation
    ai_recommendation: Mapped[CertificationDecision | None] = mapped_column(String(30))
    ai_confidence: Mapped[float | None] = mapped_column()
    ai_reasoning: Mapped[str | None] = mapped_column(Text)
    ai_risk_factors: Mapped[list | None] = mapped_column(JSON)

    # Usage stats for AI analysis
    last_used_at: Mapped[datetime | None] = mapped_column(DateTime)
    usage_count_90d: Mapped[int | None] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    campaign: Mapped["CertificationCampaign"] = relationship(back_populates="items")

    def __repr__(self) -> str:
        return f"<CertificationItem campaign={self.campaign_id} decision={self.decision}>"
