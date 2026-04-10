"""CertificationAgent — Autonomous access review and certification."""

from __future__ import annotations

from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.agents.base import AgentDecision, AgentResult, BaseAgent
from iga.config import settings
from iga.database import AsyncSessionLocal
from iga.models.policy import (
    CertificationDecision,
    CertificationItem,
    CampaignStatus,
    CertificationCampaign,
)

logger = structlog.get_logger(__name__)

CERTIFICATION_SYSTEM_PROMPT = """
You are the CertificationAgent for an Identity Governance & Administration (IGA) system.
Your role is to assist with access certification campaigns — reviewing whether users
should retain their current access.

For each access item, analyze:
1. Is this access appropriate for the user's current role and department?
2. Has this access been used recently? (unused access is a risk)
3. Does this access represent excessive privilege for the user's job function?
4. Are there any risk factors that warrant human review?

Decision options:
- "certified": Access is appropriate and should be kept
- "revoked": Access is inappropriate and should be removed
- "auto_certified": Very high confidence (>95%) the access is appropriate
- "auto_revoked": Very high confidence (>95%) the access should be removed
- "escalate": Uncertain — needs human certifier to review

Risk factors that increase the likelihood of revocation recommendation:
- Access not used in 90+ days
- User's job title doesn't align with the access
- Highly privileged access without clear business justification
- Access to systems outside the user's department
- User is a contractor with admin access

Always err on the side of caution: if uncertain, recommend human review.
"""


class CertificationAgent(BaseAgent):
    """
    Autonomous agent for running access certification campaigns.

    - Processes pending certification items within active campaigns
    - Makes AI-driven certify/revoke recommendations
    - Auto-certifies/revokes items with very high confidence
    - Escalates uncertain items to human certifiers
    """

    def __init__(self) -> None:
        super().__init__(
            name="certification",
            description="Runs access certification campaigns with AI-driven decisions",
        )

    async def run(self) -> AgentResult:
        start_time = self._start_run()
        result = AgentResult(agent_name=self.name, success=True, dry_run=self.dry_run)

        async with AsyncSessionLocal() as session:
            try:
                active_campaigns = await self._fetch_active_campaigns(session)
                self.log.info(
                    "processing_campaigns", count=len(active_campaigns)
                )

                for campaign in active_campaigns:
                    campaign_result = await self._process_campaign(session, campaign)
                    result.items_processed += campaign_result["processed"]
                    result.items_actioned += campaign_result["actioned"]
                    result.decisions.extend(campaign_result["decisions"])

                await session.commit()

            except Exception as e:
                result.success = False
                result.errors.append(str(e))
                self.log.error("certification_agent_error", error=str(e))
                await session.rollback()

        return self._end_run(result, start_time)

    async def _fetch_active_campaigns(
        self, session: AsyncSession
    ) -> list[CertificationCampaign]:
        stmt = select(CertificationCampaign).where(
            CertificationCampaign.status == CampaignStatus.ACTIVE
        )
        rows = await session.execute(stmt)
        return list(rows.scalars().all())

    async def _process_campaign(
        self, session: AsyncSession, campaign: CertificationCampaign
    ) -> dict:
        """Process all pending items in a campaign."""
        stmt = (
            select(CertificationItem)
            .where(
                CertificationItem.campaign_id == campaign.id,
                CertificationItem.decision == CertificationDecision.PENDING,
            )
            .limit(100)
        )
        rows = await session.execute(stmt)
        items = list(rows.scalars().all())

        campaign_result: dict = {"processed": len(items), "actioned": 0, "decisions": []}

        for item in items:
            decision = await self._evaluate_item(item, campaign)
            campaign_result["decisions"].append(decision)

            # Apply AI recommendation
            item.ai_recommendation = CertificationDecision(decision.action) if decision.action in [d.value for d in CertificationDecision] else CertificationDecision.PENDING
            item.ai_confidence = decision.confidence
            item.ai_reasoning = decision.reasoning

            # Auto-decide if confidence is high enough
            if (
                not self.dry_run
                and decision.action == "auto_certified"
                and decision.confidence >= campaign.auto_certify_threshold
            ):
                item.decision = CertificationDecision.AUTO_CERTIFIED
                item.decided_at = datetime.utcnow()
                campaign_result["actioned"] += 1
                campaign.ai_decided_count += 1
                campaign.certified_count += 1

            elif (
                not self.dry_run
                and decision.action == "auto_revoked"
                and decision.confidence >= campaign.auto_revoke_threshold
            ):
                item.decision = CertificationDecision.AUTO_REVOKED
                item.decided_at = datetime.utcnow()
                campaign_result["actioned"] += 1
                campaign.ai_decided_count += 1
                campaign.revoked_count += 1

            self._log_decision(decision, context_id=item.id)

        # Update campaign pending count
        campaign.pending_count = campaign.total_items - (
            campaign.certified_count + campaign.revoked_count
        )

        return campaign_result

    async def _evaluate_item(
        self, item: CertificationItem, campaign: CertificationCampaign
    ) -> AgentDecision:
        context = {
            "item_id": item.id,
            "campaign_name": campaign.name,
            "identity_id": item.identity_id,
            "role_id": item.role_id,
            "permission_id": item.permission_id,
            "application_id": item.application_id,
            "last_used_at": item.last_used_at.isoformat() if item.last_used_at else None,
            "usage_count_90d": item.usage_count_90d,
            "auto_certify_threshold": campaign.auto_certify_threshold,
            "auto_revoke_threshold": campaign.auto_revoke_threshold,
        }

        return await self.make_decision(
            system_prompt=CERTIFICATION_SYSTEM_PROMPT,
            context=context,
            decision_schema=(
                '{"action": "auto_certified|auto_revoked|escalate", '
                '"reasoning": "string", "confidence": 0.0-1.0, '
                '"requires_human_review": bool, "risk_level": "low|medium|high|critical", '
                '"data": {"risk_factors": [], "usage_assessment": "string"}}'
            ),
        )
