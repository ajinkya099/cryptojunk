"""Role and permission models: Role, Permission, Entitlement, RoleAssignment."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iga.database import Base


class RoleType(str, Enum):
    BUSINESS = "business"       # Business role (e.g. "Finance Manager")
    TECHNICAL = "technical"     # Technical/IT role (e.g. "Linux Admin")
    APPLICATION = "application" # App-specific role (e.g. "Salesforce Admin")
    PRIVILEGED = "privileged"   # High-privilege role requiring extra controls


class RoleStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    DEPRECATED = "deprecated"
    DRAFT = "draft"


class Role(Base):
    """A role in the RBAC/ABAC model."""

    __tablename__ = "roles"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    role_type: Mapped[RoleType] = mapped_column(String(20), default=RoleType.BUSINESS)
    status: Mapped[RoleStatus] = mapped_column(String(20), default=RoleStatus.ACTIVE)

    owner_id: Mapped[str | None] = mapped_column(
        String(36), ForeignKey("identities.id")
    )
    is_requestable: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_approval: Mapped[bool] = mapped_column(Boolean, default=True)
    requires_certification: Mapped[bool] = mapped_column(Boolean, default=True)
    max_assignment_duration_days: Mapped[int | None] = mapped_column()

    # Risk scoring
    risk_score: Mapped[int] = mapped_column(default=1)  # 1 (low) - 10 (critical)

    # AI-generated metadata
    ai_description: Mapped[str | None] = mapped_column(Text)
    ai_risk_reasoning: Mapped[str | None] = mapped_column(Text)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    permissions: Mapped[list["RolePermission"]] = relationship(back_populates="role")
    assignments: Mapped[list["RoleAssignment"]] = relationship(back_populates="role")

    def __repr__(self) -> str:
        return f"<Role {self.name} [{self.role_type}]>"


class Permission(Base):
    """A granular permission/entitlement on a specific application."""

    __tablename__ = "permissions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), index=True
    )
    name: Mapped[str] = mapped_column(String(255), index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    is_privileged: Mapped[bool] = mapped_column(Boolean, default=False)
    risk_score: Mapped[int] = mapped_column(default=1)

    # Metadata for AI analysis
    category: Mapped[str | None] = mapped_column(String(100))
    tags: Mapped[list | None] = mapped_column(JSON)

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    role_permissions: Mapped[list["RolePermission"]] = relationship(
        back_populates="permission"
    )

    def __repr__(self) -> str:
        return f"<Permission {self.name}>"


class RolePermission(Base):
    """Association: which permissions are included in a role."""

    __tablename__ = "role_permissions"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"), index=True)
    permission_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("permissions.id"), index=True
    )
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())

    # Relationships
    role: Mapped["Role"] = relationship(back_populates="permissions")
    permission: Mapped["Permission"] = relationship(back_populates="role_permissions")


class RoleAssignment(Base):
    """Assignment of a role to an identity."""

    __tablename__ = "role_assignments"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identities.id"), index=True
    )
    role_id: Mapped[str] = mapped_column(String(36), ForeignKey("roles.id"), index=True)

    # Assignment metadata
    assigned_by: Mapped[str | None] = mapped_column(String(100))  # user_id | "ai_agent"
    assignment_reason: Mapped[str | None] = mapped_column(Text)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    expires_at: Mapped[datetime | None] = mapped_column(DateTime)

    # AI reasoning (if AI-assigned)
    ai_reasoning: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[float | None] = mapped_column()

    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime)
    revocation_reason: Mapped[str | None] = mapped_column(Text)

    # Relationships
    identity: Mapped["Identity"] = relationship()  # type: ignore[assignment]
    role: Mapped["Role"] = relationship(back_populates="assignments")

    def __repr__(self) -> str:
        return f"<RoleAssignment identity={self.identity_id} role={self.role_id}>"
