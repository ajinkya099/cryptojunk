"""Certification service — business logic for access review campaigns."""

from __future__ import annotations

from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.config import settings
from iga.models.policy import (
    CampaignStatus,
    CertificationCampaign,
    CertificationDecision,
    CertificationItem,
)
from iga.models.access import AccessAssignment


class CertificationService:
    """Business logic for certification campaign management."""

    def __init__(self, session: AsyncSession) -> None:
        self.session = session

    async def create_campaign(
        self,
        name: str,
        scope_applications: list[str] | None = None,
        scope_roles: list[str] | None = None,
        scope_departments: list[str] | None = None,
        duration_days: int | None = None,
        owner_id: str | None = None,
    ) -> CertificationCampaign:
        """Create a new certification campaign."""
        duration = duration_days or settings.cert_campaign_default_duration_days
        campaign = CertificationCampaign(
            name=name,
            status=CampaignStatus.DRAFT,
            scope_applications=scope_applications,
            scope_roles=scope_roles,
            scope_departments=scope_departments,
            duration_days=duration,
            owner_id=owner_id,
            auto_certify_threshold=settings.cert_campaign_auto_approve_threshold,
            auto_revoke_threshold=settings.cert_campaign_auto_revoke_threshold,
            ai_assist_enabled=True,
        )
        self.session.add(campaign)
        await self.session.flush()
        return campaign

    async def launch_campaign(
        self, campaign_id: str
    ) -> CertificationCampaign | None:
        """Launch a draft campaign — generate items and set to ACTIVE."""
        campaign = await self._get_campaign(campaign_id)
        if not campaign or campaign.status != CampaignStatus.DRAFT:
            return None

        # Generate certification items from access assignments
        items = await self._generate_items(campaign)
        campaign.status = CampaignStatus.ACTIVE
        campaign.start_date = datetime.utcnow()
        campaign.end_date = datetime.utcnow() + timedelta(days=campaign.duration_days)
        campaign.total_items = len(items)
        campaign.pending_count = len(items)

        return campaign

    async def get_campaign_progress(self, campaign_id: str) -> dict | None:
        campaign = await self._get_campaign(campaign_id)
        if not campaign:
            return None

        return {
            "campaign_id": campaign.id,
            "name": campaign.name,
            "status": campaign.status,
            "total_items": campaign.total_items,
            "certified_count": campaign.certified_count,
            "revoked_count": campaign.revoked_count,
            "pending_count": campaign.pending_count,
            "ai_decided_count": campaign.ai_decided_count,
            "completion_pct": (
                round(
                    (campaign.certified_count + campaign.revoked_count)
                    / max(campaign.total_items, 1)
                    * 100,
                    1,
                )
            ),
            "end_date": campaign.end_date.isoformat() if campaign.end_date else None,
        }

    async def submit_decision(
        self,
        item_id: str,
        decision: CertificationDecision,
        certifier_id: str,
        reason: str | None = None,
    ) -> CertificationItem | None:
        """Submit a human certifier decision on an item."""
        stmt = select(CertificationItem).where(CertificationItem.id == item_id)
        row = await self.session.execute(stmt)
        item = row.scalar_one_or_none()

        if not item or item.decision != CertificationDecision.PENDING:
            return None

        item.decision = decision
        item.certifier_id = certifier_id
        item.decision_reason = reason
        item.decided_at = datetime.utcnow()

        # Update campaign stats
        campaign = await self._get_campaign(item.campaign_id)
        if campaign:
            if decision in (CertificationDecision.CERTIFIED, CertificationDecision.AUTO_CERTIFIED):
                campaign.certified_count += 1
            elif decision in (CertificationDecision.REVOKED, CertificationDecision.AUTO_REVOKED):
                campaign.revoked_count += 1
            campaign.pending_count = max(0, campaign.pending_count - 1)

            # Auto-complete if all items decided
            if campaign.pending_count == 0:
                campaign.status = CampaignStatus.COMPLETED

        return item

    async def _get_campaign(self, campaign_id: str) -> CertificationCampaign | None:
        stmt = select(CertificationCampaign).where(
            CertificationCampaign.id == campaign_id
        )
        row = await self.session.execute(stmt)
        return row.scalar_one_or_none()

    async def _generate_items(
        self, campaign: CertificationCampaign
    ) -> list[CertificationItem]:
        """Generate certification items from active access assignments in scope."""
        stmt = select(AccessAssignment).where(
            AccessAssignment.is_active == True  # noqa: E712
        )
        if campaign.scope_applications:
            stmt = stmt.where(
                AccessAssignment.application_id.in_(campaign.scope_applications)
            )
        if campaign.scope_roles:
            stmt = stmt.where(
                AccessAssignment.role_id.in_(campaign.scope_roles)
            )

        rows = await self.session.execute(stmt)
        assignments = list(rows.scalars().all())

        items = []
        for assignment in assignments:
            item = CertificationItem(
                campaign_id=campaign.id,
                identity_id=assignment.identity_id,
                access_assignment_id=assignment.id,
                role_id=assignment.role_id,
                permission_id=assignment.permission_id,
                application_id=assignment.application_id,
                decision=CertificationDecision.PENDING,
                last_used_at=assignment.last_certified_at,
            )
            self.session.add(item)
            items.append(item)

        await self.session.flush()
        return items
