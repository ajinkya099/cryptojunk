"""Tests for identity API endpoints."""

import pytest


@pytest.mark.asyncio
async def test_health_check(client):
    response = await client.get("/health")
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"


@pytest.mark.asyncio
async def test_list_identities_empty(client):
    response = await client.get("/api/v1/identities")
    assert response.status_code == 200
    assert isinstance(response.json(), list)


@pytest.mark.asyncio
async def test_create_joiner_event(client):
    response = await client.post(
        "/api/v1/identities/joiner",
        json={
            "identity": {
                "email": "newuser@example.com",
                "display_name": "New User",
                "first_name": "New",
                "last_name": "User",
                "department": "Engineering",
                "job_title": "Software Engineer",
                "employee_id": "EMP001",
            },
            "triggered_by": "test",
        },
    )
    assert response.status_code == 201
    data = response.json()
    assert "event_id" in data
    assert data["type"] == "joiner"
    assert data["status"] == "pending"


@pytest.mark.asyncio
async def test_create_leaver_event(client):
    # First create an identity via joiner
    joiner_resp = await client.post(
        "/api/v1/identities/joiner",
        json={
            "identity": {
                "email": "leaver@example.com",
                "display_name": "Leaving User",
                "employee_id": "EMP002",
            },
            "triggered_by": "test",
        },
    )
    assert joiner_resp.status_code == 201

    # Get the identity
    identities = await client.get("/api/v1/identities")
    identities_data = identities.json()
    leaver_identity = next(
        (i for i in identities_data if i["email"] == "leaver@example.com"), None
    )
    assert leaver_identity is not None

    # Create leaver event
    leaver_resp = await client.post(
        "/api/v1/identities/leaver",
        json={
            "identity_id": leaver_identity["id"],
            "reason": "Resignation",
            "triggered_by": "test",
        },
    )
    assert leaver_resp.status_code == 201
    data = leaver_resp.json()
    assert data["type"] == "leaver"


@pytest.mark.asyncio
async def test_get_identity_not_found(client):
    response = await client.get("/api/v1/identities/nonexistent-id")
    assert response.status_code == 404


@pytest.mark.asyncio
async def test_agent_status(client):
    response = await client.get("/api/v1/agents/status")
    assert response.status_code == 200
    data = response.json()
    assert "agents" in data
    assert "lifecycle" in data["agents"]
    assert "sod_detector" in data["agents"]
