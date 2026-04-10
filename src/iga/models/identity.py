"""Identity models: User, Account, Application."""

import uuid
from datetime import datetime
from enum import Enum

from sqlalchemy import Boolean, DateTime, ForeignKey, String, Text, func
from sqlalchemy.dialects.sqlite import JSON
from sqlalchemy.orm import Mapped, mapped_column, relationship

from iga.database import Base


class IdentityStatus(str, Enum):
    ACTIVE = "active"
    INACTIVE = "inactive"
    SUSPENDED = "suspended"
    PENDING = "pending"


class LifecycleEventType(str, Enum):
    JOINER = "joiner"
    MOVER = "mover"
    LEAVER = "leaver"
    REHIRE = "rehire"
    CONTRACT_CHANGE = "contract_change"


class LifecycleEventStatus(str, Enum):
    PENDING = "pending"
    IN_PROGRESS = "in_progress"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


class Identity(Base):
    """A person/entity managed by the IGA system."""

    __tablename__ = "identities"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    external_id: Mapped[str | None] = mapped_column(String(255), unique=True, index=True)
    email: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    first_name: Mapped[str | None] = mapped_column(String(100))
    last_name: Mapped[str | None] = mapped_column(String(100))

    # Employment
    employee_id: Mapped[str | None] = mapped_column(String(100), unique=True, index=True)
    department: Mapped[str | None] = mapped_column(String(255))
    job_title: Mapped[str | None] = mapped_column(String(255))
    manager_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("identities.id"))
    location: Mapped[str | None] = mapped_column(String(255))
    cost_center: Mapped[str | None] = mapped_column(String(100))

    # Status
    status: Mapped[IdentityStatus] = mapped_column(
        String(20), default=IdentityStatus.PENDING
    )
    is_privileged: Mapped[bool] = mapped_column(Boolean, default=False)
    is_service_account: Mapped[bool] = mapped_column(Boolean, default=False)

    # Dates
    hire_date: Mapped[datetime | None] = mapped_column(DateTime)
    termination_date: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Extended attributes (flexible JSON)
    attributes: Mapped[dict | None] = mapped_column(JSON)

    # Relationships
    accounts: Mapped[list["Account"]] = relationship(back_populates="identity")
    lifecycle_events: Mapped[list["LifecycleEvent"]] = relationship(
        back_populates="identity"
    )
    access_assignments: Mapped[list["AccessAssignment"]] = relationship(  # noqa: F821
        back_populates="identity", foreign_keys="AccessAssignment.identity_id"
    )

    def __repr__(self) -> str:
        return f"<Identity {self.email} [{self.status}]>"


class Application(Base):
    """A business application managed by IGA."""

    __tablename__ = "applications"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    name: Mapped[str] = mapped_column(String(255), unique=True, index=True)
    display_name: Mapped[str] = mapped_column(String(255))
    description: Mapped[str | None] = mapped_column(Text)
    owner_id: Mapped[str | None] = mapped_column(String(36), ForeignKey("identities.id"))
    is_critical: Mapped[bool] = mapped_column(Boolean, default=False)
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    connector_type: Mapped[str | None] = mapped_column(String(100))
    config: Mapped[dict | None] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    accounts: Mapped[list["Account"]] = relationship(back_populates="application")

    def __repr__(self) -> str:
        return f"<Application {self.name}>"


class Account(Base):
    """A user account on a specific application."""

    __tablename__ = "accounts"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    identity_id: Mapped[str] = mapped_column(String(36), ForeignKey("identities.id"), index=True)
    application_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("applications.id"), index=True
    )
    username: Mapped[str] = mapped_column(String(255))
    is_active: Mapped[bool] = mapped_column(Boolean, default=True)
    is_privileged: Mapped[bool] = mapped_column(Boolean, default=False)
    last_login: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    # Relationships
    identity: Mapped["Identity"] = relationship(back_populates="accounts")
    application: Mapped["Application"] = relationship(back_populates="accounts")

    def __repr__(self) -> str:
        return f"<Account {self.username}@{self.application_id}>"


class LifecycleEvent(Base):
    """A JML (Joiner/Mover/Leaver) event for an identity."""

    __tablename__ = "lifecycle_events"

    id: Mapped[str] = mapped_column(
        String(36), primary_key=True, default=lambda: str(uuid.uuid4())
    )
    identity_id: Mapped[str] = mapped_column(
        String(36), ForeignKey("identities.id"), index=True
    )
    event_type: Mapped[LifecycleEventType] = mapped_column(String(30))
    status: Mapped[LifecycleEventStatus] = mapped_column(
        String(20), default=LifecycleEventStatus.PENDING
    )

    # Event data
    triggered_by: Mapped[str | None] = mapped_column(String(100))  # system | user_id
    payload: Mapped[dict | None] = mapped_column(JSON)  # HR system data

    # AI decision
    ai_decision: Mapped[str | None] = mapped_column(Text)
    ai_reasoning: Mapped[str | None] = mapped_column(Text)
    ai_confidence: Mapped[float | None] = mapped_column()

    # Timestamps
    scheduled_at: Mapped[datetime | None] = mapped_column(DateTime)
    processed_at: Mapped[datetime | None] = mapped_column(DateTime)
    created_at: Mapped[datetime] = mapped_column(DateTime, server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(
        DateTime, server_default=func.now(), onupdate=func.now()
    )

    error_message: Mapped[str | None] = mapped_column(Text)

    # Relationships
    identity: Mapped["Identity"] = relationship(back_populates="lifecycle_events")

    def __repr__(self) -> str:
        return f"<LifecycleEvent {self.event_type} for {self.identity_id} [{self.status}]>"
