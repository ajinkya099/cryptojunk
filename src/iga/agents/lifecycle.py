"""LifecycleAgent — Autonomous Joiner/Mover/Leaver processing."""

from __future__ import annotations

from datetime import datetime

import structlog
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from iga.agents.base import AgentDecision, AgentResult, BaseAgent
from iga.database import AsyncSessionLocal
from iga.models.identity import LifecycleEvent, LifecycleEventStatus, LifecycleEventType

logger = structlog.get_logger(__name__)

LIFECYCLE_SYSTEM_PROMPT = """
You are the LifecycleAgent for an Identity Governance & Administration (IGA) system.
Your job is to process Joiner/Mover/Leaver (JML) events for employees and contractors.

Your responsibilities:
- JOINER: Determine appropriate initial access based on job title, department, and location
- MOVER: Determine what access to add, remove, or modify based on role change details
- LEAVER: Determine what access to revoke and in what order (immediate vs graceful)

Decision guidelines:
- Privileged access (admin, root, financial systems) must be revoked IMMEDIATELY on leaver events
- Standard access can be revoked within the SLA (typically same business day)
- For joiners, apply least-privilege: only grant what the job role genuinely requires
- For movers, always clean up old access before granting new (avoid accumulation)
- Flag anything unusual (e.g. contractor getting admin access, leaver still in active systems)

Always reason step by step and provide a confidence score (0.0-1.0).
"""


class LifecycleAgent(BaseAgent):
    """
    Autonomous agent for processing Joiner/Mover/Leaver events.

    Runs every 5 minutes via Celery Beat, processes all PENDING lifecycle events,
    makes AI-driven decisions on what access to grant/revoke, and executes
    provisioning actions (or logs them in dry_run mode).
    """

    def __init__(self) -> None:
        super().__init__(
            name="lifecycle",
            description="Processes JML events and makes access provisioning decisions",
        )

    async def run(self) -> AgentResult:
        start_time = self._start_run()
        result = AgentResult(agent_name=self.name, success=True, dry_run=self.dry_run)

        async with AsyncSessionLocal() as session:
            try:
                pending_events = await self._fetch_pending_events(session)
                result.items_processed = len(pending_events)
                self.log.info("processing_lifecycle_events", count=len(pending_events))

                for event in pending_events:
                    decision = await self._process_event(session, event)
                    result.decisions.append(decision)
                    if decision.action != "skip":
                        result.items_actioned += 1

                await session.commit()

            except Exception as e:
                result.success = False
                result.errors.append(str(e))
                self.log.error("lifecycle_agent_error", error=str(e))
                await session.rollback()

        return self._end_run(result, start_time)

    async def _fetch_pending_events(self, session: AsyncSession) -> list[LifecycleEvent]:
        stmt = (
            select(LifecycleEvent)
            .where(LifecycleEvent.status == LifecycleEventStatus.PENDING)
            .order_by(LifecycleEvent.created_at)
            .limit(50)  # Process in batches
        )
        rows = await session.execute(stmt)
        return list(rows.scalars().all())

    async def _process_event(
        self, session: AsyncSession, event: LifecycleEvent
    ) -> AgentDecision:
        context = {
            "event_id": event.id,
            "event_type": event.event_type,
            "identity_id": event.identity_id,
            "payload": event.payload or {},
            "scheduled_at": event.scheduled_at.isoformat() if event.scheduled_at else None,
            "triggered_by": event.triggered_by,
        }

        decision = await self.make_decision(
            system_prompt=LIFECYCLE_SYSTEM_PROMPT,
            context=context,
            decision_schema=(
                '{"action": "provision_access|revoke_access|modify_access|escalate|skip", '
                '"reasoning": "string", "confidence": 0.0-1.0, '
                '"requires_human_review": bool, "risk_level": "low|medium|high|critical", '
                '"data": {"roles_to_grant": [], "roles_to_revoke": [], '
                '"immediate_revoke": [], "notes": "string"}}'
            ),
        )

        self._log_decision(decision, context_id=event.id)

        # Update event with AI decision
        event.ai_decision = decision.action
        event.ai_reasoning = decision.reasoning
        event.ai_confidence = decision.confidence

        if self.dry_run:
            # Dry run: mark as completed but don't actually provision
            event.status = LifecycleEventStatus.COMPLETED
            event.processed_at = datetime.utcnow()
            self.log.info(
                "dry_run_lifecycle",
                event_id=event.id,
                event_type=event.event_type,
                action=decision.action,
            )
        elif decision.requires_human_review or not decision.is_high_confidence():
            # Low confidence or needs review: escalate
            event.status = LifecycleEventStatus.PENDING
            self.log.warning(
                "lifecycle_needs_review",
                event_id=event.id,
                confidence=decision.confidence,
            )
        else:
            # High confidence: execute the decision
            await self._execute_decision(session, event, decision)
            event.status = LifecycleEventStatus.COMPLETED
            event.processed_at = datetime.utcnow()

        return decision

    async def _execute_decision(
        self,
        session: AsyncSession,
        event: LifecycleEvent,
        decision: AgentDecision,
    ) -> None:
        """
        Execute provisioning actions.
        In production this would call provisioning connectors.
        """
        action_data = decision.data
        self.log.info(
            "executing_lifecycle_decision",
            event_id=event.id,
            event_type=event.event_type,
            action=decision.action,
            roles_to_grant=action_data.get("roles_to_grant", []),
            roles_to_revoke=action_data.get("roles_to_revoke", []),
            immediate_revoke=action_data.get("immediate_revoke", []),
        )
        # TODO: Call provisioning service to apply changes
        # await provisioning_service.apply(event.identity_id, action_data)
