"""
Seed script — populate the database with sample IGA data for development/demo.

Usage:
    PYTHONPATH=src python -m iga.scripts.seed_data
"""

from __future__ import annotations

import asyncio

from iga.database import AsyncSessionLocal, create_tables
from iga.models.identity import Identity, IdentityStatus
from iga.models.policy import SoDPolicy, SoDViolationSeverity
from iga.models.role import Permission, Role, RolePermission, RoleType
from iga.services.lifecycle import LifecycleService
from iga.services.role_management import RoleManagementService
from iga.services.sod import SoDService


SAMPLE_ROLES = [
    {"name": "finance-viewer", "display_name": "Finance Viewer", "risk_score": 3, "type": RoleType.BUSINESS},
    {"name": "finance-approver", "display_name": "Finance Approver", "risk_score": 7, "type": RoleType.BUSINESS},
    {"name": "hr-admin", "display_name": "HR Administrator", "risk_score": 5, "type": RoleType.BUSINESS},
    {"name": "it-admin", "display_name": "IT Administrator", "risk_score": 8, "type": RoleType.TECHNICAL},
    {"name": "db-reader", "display_name": "Database Reader", "risk_score": 4, "type": RoleType.TECHNICAL},
    {"name": "db-writer", "display_name": "Database Writer", "risk_score": 7, "type": RoleType.TECHNICAL},
    {"name": "deploy-production", "display_name": "Deploy to Production", "risk_score": 9, "type": RoleType.PRIVILEGED},
    {"name": "code-committer", "display_name": "Code Committer", "risk_score": 3, "type": RoleType.TECHNICAL},
]

SAMPLE_SOD_POLICIES = [
    {
        "name": "finance-create-approve",
        "description": "User cannot both create and approve financial transactions",
        "severity": SoDViolationSeverity.CRITICAL,
        "side_a_roles": ["finance-viewer"],
        "side_b_roles": ["finance-approver"],
        "guidance": "Remove finance-approver from users who can also initiate transactions",
    },
    {
        "name": "dev-deploy-sod",
        "description": "Developers should not directly deploy to production",
        "severity": SoDViolationSeverity.HIGH,
        "side_a_roles": ["code-committer"],
        "side_b_roles": ["deploy-production"],
        "guidance": "Revoke deploy-production from developers. Use a deployment service account.",
    },
    {
        "name": "db-read-write-sod",
        "description": "Limit users who have both read and write access to production databases",
        "severity": SoDViolationSeverity.MEDIUM,
        "side_a_roles": ["db-reader"],
        "side_b_roles": ["db-writer"],
        "guidance": "Review if user genuinely needs both. DBA role should use write; analysts use read.",
    },
]

SAMPLE_IDENTITIES = [
    {"email": "alice@example.com", "display_name": "Alice Johnson", "department": "Finance", "job_title": "Financial Analyst", "employee_id": "E001"},
    {"email": "bob@example.com", "display_name": "Bob Smith", "department": "Engineering", "job_title": "Software Engineer", "employee_id": "E002"},
    {"email": "carol@example.com", "display_name": "Carol Davis", "department": "HR", "job_title": "HR Manager", "employee_id": "E003"},
    {"email": "dave@example.com", "display_name": "Dave Wilson", "department": "IT", "job_title": "IT Administrator", "employee_id": "E004"},
]


async def seed() -> None:
    print("Creating tables...")
    await create_tables()

    async with AsyncSessionLocal() as session:
        role_svc = RoleManagementService(session)
        sod_svc = SoDService(session)
        lifecycle_svc = LifecycleService(session)

        print("Seeding roles...")
        role_map: dict[str, Role] = {}
        for r in SAMPLE_ROLES:
            role = await role_svc.create_role(
                name=r["name"],
                display_name=r["display_name"],
                role_type=r["type"],
                risk_score=r["risk_score"],
            )
            role_map[r["name"]] = role
        await session.commit()
        print(f"  Created {len(role_map)} roles")

        print("Seeding SoD policies...")
        for p in SAMPLE_SOD_POLICIES:
            await sod_svc.create_policy(
                name=p["name"],
                description=p["description"],
                severity=p["severity"],
                side_a_roles=[role_map[r].id for r in p["side_a_roles"] if r in role_map],
                side_b_roles=[role_map[r].id for r in p["side_b_roles"] if r in role_map],
                remediation_guidance=p["guidance"],
            )
        await session.commit()
        print(f"  Created {len(SAMPLE_SOD_POLICIES)} SoD policies")

        print("Seeding identities via joiner events...")
        for identity_data in SAMPLE_IDENTITIES:
            await lifecycle_svc.create_joiner_event(
                identity_data=identity_data,
                triggered_by="seed_script",
            )
        await session.commit()
        print(f"  Created {len(SAMPLE_IDENTITIES)} joiner events")

    print("\nSeed complete! Start the API and agents with: make dev")
    print("API docs: http://localhost:8000/docs")
    print("Agent control: http://localhost:8000/api/v1/agents/status")


if __name__ == "__main__":
    asyncio.run(seed())
