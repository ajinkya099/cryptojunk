"""
Celery task definitions for AISm autonomous agents.

This module defines:
- Celery app configuration
- Async-compatible task wrappers for each agent
- Beat schedule for 24/7 autonomous operation
"""

from __future__ import annotations

import asyncio
from typing import Any

import structlog
from celery import Celery
from celery.schedules import crontab

from iga.config import settings

logger = structlog.get_logger("celery.tasks")

# ── Celery App ────────────────────────────────────────────────────
app = Celery(
    "iga_workers",
    broker=settings.celery_broker_url,
    backend=settings.celery_result_backend,
)

app.conf.update(
    task_serializer="json",
    accept_content=["json"],
    result_serializer="json",
    timezone="UTC",
    enable_utc=True,
    task_track_started=True,
    task_acks_late=True,
    worker_prefetch_multiplier=1,
    task_routes={
        "iga.workers.tasks.run_lifecycle_agent": {"queue": "agents"},
        "iga.workers.tasks.run_certification_agent": {"queue": "agents"},
        "iga.workers.tasks.run_sod_detector_agent": {"queue": "agents"},
        "iga.workers.tasks.run_role_miner_agent": {"queue": "agents"},
        "iga.workers.tasks.assess_access_request": {"queue": "realtime"},
    },
)

# ── Beat Schedule — 24/7 Autonomous Operation ─────────────────────
app.conf.beat_schedule = {
    # Lifecycle Agent: every 5 minutes
    "lifecycle-agent-every-5-min": {
        "task": "iga.workers.tasks.run_lifecycle_agent",
        "schedule": crontab(minute="*/5"),
        "options": {"queue": "agents"},
    },
    # SoD Detector: every 30 minutes
    "sod-detector-every-30-min": {
        "task": "iga.workers.tasks.run_sod_detector_agent",
        "schedule": crontab(minute="*/30"),
        "options": {"queue": "agents"},
    },
    # Certification Agent: daily at 2:00 AM UTC
    "certification-agent-daily-2am": {
        "task": "iga.workers.tasks.run_certification_agent",
        "schedule": crontab(hour=2, minute=0),
        "options": {"queue": "agents"},
    },
    # Role Miner: weekly on Sunday at 1:00 AM UTC
    "role-miner-weekly-sunday": {
        "task": "iga.workers.tasks.run_role_miner_agent",
        "schedule": crontab(hour=1, minute=0, day_of_week=0),
        "options": {"queue": "agents"},
    },
    # Emergency SoD scan: every hour at :00 (belt-and-suspenders)
    "sod-hourly-check": {
        "task": "iga.workers.tasks.run_sod_detector_agent",
        "schedule": crontab(minute=0),
        "options": {"queue": "agents"},
    },
}


def _run_async(coro) -> Any:
    """Helper to run async code from sync Celery tasks."""
    try:
        loop = asyncio.get_event_loop()
        if loop.is_running():
            # If already in an event loop, create a new thread
            import concurrent.futures
            with concurrent.futures.ThreadPoolExecutor() as pool:
                future = pool.submit(asyncio.run, coro)
                return future.result()
        return loop.run_until_complete(coro)
    except RuntimeError:
        return asyncio.run(coro)


# ── Agent Tasks ───────────────────────────────────────────────────

@app.task(
    name="iga.workers.tasks.run_lifecycle_agent",
    bind=True,
    max_retries=3,
    default_retry_delay=60,
)
def run_lifecycle_agent(self) -> dict[str, Any]:
    """Celery task: Run the LifecycleAgent to process pending JML events."""
    from iga.agents.lifecycle import LifecycleAgent

    logger.info("celery_task_started", task="lifecycle_agent")
    try:
        agent = LifecycleAgent()
        result = _run_async(agent.run())
        logger.info("celery_task_completed", task="lifecycle_agent", summary=result.summary())
        return {
            "success": result.success,
            "items_processed": result.items_processed,
            "items_actioned": result.items_actioned,
            "errors": result.errors,
            "duration_seconds": result.duration_seconds,
        }
    except Exception as exc:
        logger.error("celery_task_failed", task="lifecycle_agent", error=str(exc))
        raise self.retry(exc=exc)


@app.task(
    name="iga.workers.tasks.run_certification_agent",
    bind=True,
    max_retries=3,
    default_retry_delay=300,
)
def run_certification_agent(self) -> dict[str, Any]:
    """Celery task: Run the CertificationAgent to process active campaigns."""
    from iga.agents.certification import CertificationAgent

    logger.info("celery_task_started", task="certification_agent")
    try:
        agent = CertificationAgent()
        result = _run_async(agent.run())
        logger.info("celery_task_completed", task="certification_agent", summary=result.summary())
        return {
            "success": result.success,
            "items_processed": result.items_processed,
            "items_actioned": result.items_actioned,
            "errors": result.errors,
        }
    except Exception as exc:
        logger.error("celery_task_failed", task="certification_agent", error=str(exc))
        raise self.retry(exc=exc)


@app.task(
    name="iga.workers.tasks.run_sod_detector_agent",
    bind=True,
    max_retries=3,
    default_retry_delay=120,
)
def run_sod_detector_agent(self) -> dict[str, Any]:
    """Celery task: Run the SoDDetectorAgent to scan for violations."""
    from iga.agents.sod_detector import SoDDetectorAgent

    logger.info("celery_task_started", task="sod_detector_agent")
    try:
        agent = SoDDetectorAgent()
        result = _run_async(agent.run())
        logger.info("celery_task_completed", task="sod_detector_agent", summary=result.summary())
        return {
            "success": result.success,
            "violations_detected": result.items_actioned,
            "identities_scanned": result.items_processed,
            "errors": result.errors,
        }
    except Exception as exc:
        logger.error("celery_task_failed", task="sod_detector_agent", error=str(exc))
        raise self.retry(exc=exc)


@app.task(
    name="iga.workers.tasks.run_role_miner_agent",
    bind=True,
    max_retries=2,
    default_retry_delay=600,
)
def run_role_miner_agent(self) -> dict[str, Any]:
    """Celery task: Run the RoleMinerAgent for weekly role discovery."""
    from iga.agents.role_miner import RoleMinerAgent

    logger.info("celery_task_started", task="role_miner_agent")
    try:
        agent = RoleMinerAgent()
        result = _run_async(agent.run())
        logger.info("celery_task_completed", task="role_miner_agent", summary=result.summary())
        return {
            "success": result.success,
            "roles_analyzed": result.items_processed,
            "roles_updated": result.items_actioned,
            "errors": result.errors,
        }
    except Exception as exc:
        logger.error("celery_task_failed", task="role_miner_agent", error=str(exc))
        raise self.retry(exc=exc)


@app.task(
    name="iga.workers.tasks.assess_access_request",
    bind=True,
    max_retries=3,
    default_retry_delay=30,
)
def assess_access_request(self, request_id: str) -> dict[str, Any]:
    """
    Celery task: Run AI risk assessment on a new access request.
    Triggered immediately when a new AccessRequest is created.
    """
    from iga.agents.base import BaseAgent, AgentDecision
    from iga.database import AsyncSessionLocal
    from iga.models.access import AccessRequest

    logger.info("celery_task_started", task="assess_access_request", request_id=request_id)

    async def _assess():
        from sqlalchemy import select
        from iga.agents.base import AgentDecision
        import anthropic

        async with AsyncSessionLocal() as session:
            stmt = select(AccessRequest).where(AccessRequest.id == request_id)
            row = await session.execute(stmt)
            ar = row.scalar_one_or_none()
            if not ar:
                return {"error": "Access request not found"}

            client = anthropic.AsyncAnthropic(api_key=settings.anthropic_api_key)
            prompt = f"""
You are an IGA access risk assessor. Evaluate this access request:
- Requester: {ar.requester_id}
- Beneficiary: {ar.beneficiary_id}
- Role requested: {ar.role_id}
- Permission requested: {ar.permission_id}
- Application: {ar.application_id}
- Business justification: {ar.business_justification}

Assess the risk and recommend approve, reject, or escalate.
Return JSON: {{"recommendation": "approve|reject|escalate", "risk_score": 0.0-10.0,
"reasoning": "string", "sod_conflicts": []}}
"""
            response = await client.messages.create(
                model=settings.agent_model,
                max_tokens=1024,
                messages=[{"role": "user", "content": prompt}],
            )

            import json
            try:
                parsed = json.loads(response.content[0].text)
                ar.ai_recommendation = parsed.get("recommendation")
                ar.ai_risk_score = parsed.get("risk_score")
                ar.ai_reasoning = parsed.get("reasoning")
                ar.ai_sod_conflicts = parsed.get("sod_conflicts", [])
                await session.commit()
                return parsed
            except (json.JSONDecodeError, Exception) as e:
                return {"error": str(e)}

    try:
        return _run_async(_assess())
    except Exception as exc:
        logger.error("access_request_assessment_failed", request_id=request_id, error=str(exc))
        raise self.retry(exc=exc)


def run_worker() -> None:
    """Entry point for running the Celery worker."""
    app.start(argv=["worker", "--loglevel=info", "-Q", "agents,realtime"])
