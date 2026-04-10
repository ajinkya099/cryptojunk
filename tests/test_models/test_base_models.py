"""Tests for database model creation and relationships."""

import pytest
from sqlalchemy import select

from iga.models.identity import Identity, IdentityStatus, LifecycleEvent, LifecycleEventType
from iga.models.role import Role, RoleType, RoleStatus, RoleAssignment
from iga.models.policy import SoDPolicy, SoDViolationSeverity


@pytest.mark.asyncio
async def test_create_identity(db_session):
    identity = Identity(
        email="test@example.com",
        display_name="Test User",
        department="Engineering",
        job_title="Engineer",
        status=IdentityStatus.ACTIVE,
    )
    db_session.add(identity)
    await db_session.flush()

    assert identity.id is not None
    assert identity.email == "test@example.com"
    assert identity.status == IdentityStatus.ACTIVE


@pytest.mark.asyncio
async def test_create_role(db_session):
    role = Role(
        name="test-engineer",
        display_name="Test Engineer",
        role_type=RoleType.BUSINESS,
        risk_score=3,
        status=RoleStatus.ACTIVE,
    )
    db_session.add(role)
    await db_session.flush()

    assert role.id is not None
    assert role.name == "test-engineer"
    assert role.risk_score == 3


@pytest.mark.asyncio
async def test_create_sod_policy(db_session):
    policy = SoDPolicy(
        name="test-sod-policy",
        description="Test SoD Policy",
        severity=SoDViolationSeverity.HIGH,
        side_a_roles=["role-a"],
        side_b_roles=["role-b"],
        is_active=True,
    )
    db_session.add(policy)
    await db_session.flush()

    assert policy.id is not None
    assert policy.severity == SoDViolationSeverity.HIGH
    assert "role-a" in policy.side_a_roles


@pytest.mark.asyncio
async def test_lifecycle_event(db_session):
    identity = Identity(
        email="event-test@example.com",
        display_name="Event Test User",
        status=IdentityStatus.PENDING,
    )
    db_session.add(identity)
    await db_session.flush()

    event = LifecycleEvent(
        identity_id=identity.id,
        event_type=LifecycleEventType.JOINER,
        triggered_by="test",
        payload={"department": "Engineering"},
    )
    db_session.add(event)
    await db_session.flush()

    assert event.id is not None
    assert event.identity_id == identity.id
    assert event.event_type == LifecycleEventType.JOINER
