"""AISm Agent control API — trigger, status, and monitoring endpoints."""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException
from pydantic import BaseModel

from iga.agents.orchestrator import orchestrator

router = APIRouter()


class AgentRunRequest(BaseModel):
    agent: str  # lifecycle | certification | sod_detector | role_miner | all
    parallel: bool = False


@router.get("/status")
async def agent_status() -> dict[str, Any]:
    """Get the current status of all AISm agents."""
    return orchestrator.get_status()


@router.post("/run")
async def run_agent(
    request: AgentRunRequest, background_tasks: BackgroundTasks
) -> dict[str, Any]:
    """
    Trigger an agent run.

    Use agent='all' to run all agents.
    Runs in the background — check /status for results.
    """
    valid_agents = {"lifecycle", "certification", "sod_detector", "role_miner", "all"}
    if request.agent not in valid_agents:
        raise HTTPException(
            status_code=400,
            detail=f"Unknown agent '{request.agent}'. Valid: {valid_agents}",
        )

    if request.agent == "all":
        background_tasks.add_task(orchestrator.run_all, parallel=request.parallel)
        return {
            "status": "queued",
            "message": "All agents queued for execution",
            "parallel": request.parallel,
        }
    else:
        background_tasks.add_task(orchestrator.run_agent, request.agent)
        return {
            "status": "queued",
            "agent": request.agent,
            "message": f"Agent '{request.agent}' queued for execution",
        }


@router.post("/emergency/sod-scan")
async def emergency_sod_scan(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Trigger an immediate SoD violation scan (e.g., after bulk access changes)."""
    background_tasks.add_task(orchestrator.run_emergency_sod_scan)
    return {
        "status": "queued",
        "message": "Emergency SoD scan initiated",
    }


@router.post("/emergency/lifecycle-flush")
async def lifecycle_flush(background_tasks: BackgroundTasks) -> dict[str, str]:
    """Process all pending lifecycle events immediately."""
    background_tasks.add_task(orchestrator.run_lifecycle_flush)
    return {
        "status": "queued",
        "message": "Lifecycle flush initiated — processing all pending JML events",
    }


@router.get("/history")
async def agent_history(limit: int = 20) -> list[dict[str, Any]]:
    """Get recent agent run history."""
    history = orchestrator.run_history[-limit:]
    return list(reversed(history))
