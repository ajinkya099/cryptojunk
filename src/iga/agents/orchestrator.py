"""AgentOrchestrator — Master coordinator for all AISm autonomous agents."""

from __future__ import annotations

import asyncio
from datetime import datetime, timedelta
from typing import Any

import structlog

from iga.agents.base import AgentResult
from iga.agents.certification import CertificationAgent
from iga.agents.dev_agent import DevAgent
from iga.agents.lifecycle import LifecycleAgent
from iga.agents.role_miner import RoleMinerAgent
from iga.agents.sod_detector import SoDDetectorAgent
from iga.config import settings

logger = structlog.get_logger("agent.orchestrator")


class AgentOrchestrator:
    """
    Master orchestrator for all AISm autonomous agents.

    Responsibilities:
    - Start and stop all agents on schedule
    - Handle agent failures and retries
    - Aggregate agent results for monitoring
    - Enforce agent priority and resource limits
    - Provide a single control plane for the AI development system
    """

    def __init__(self) -> None:
        self.agents = {
            "lifecycle": LifecycleAgent(),
            "certification": CertificationAgent(),
            "sod_detector": SoDDetectorAgent(),
            "role_miner": RoleMinerAgent(),
            "dev_agent": DevAgent(),
        }
        self.run_history: list[dict[str, Any]] = []
        self.log = structlog.get_logger("orchestrator")

    async def run_agent(self, agent_name: str) -> AgentResult | None:
        """Run a single agent by name."""
        agent = self.agents.get(agent_name)
        if not agent:
            self.log.error("unknown_agent", agent=agent_name)
            return None

        self.log.info("orchestrator_starting_agent", agent=agent_name)
        try:
            result = await agent.run()
            self._record_run(agent_name, result)
            return result
        except Exception as e:
            self.log.error("agent_failed", agent=agent_name, error=str(e))
            return AgentResult(
                agent_name=agent_name,
                success=False,
                errors=[str(e)],
                dry_run=settings.agent_dry_run,
            )

    async def run_all(self, parallel: bool = False) -> dict[str, AgentResult]:
        """
        Run all agents.

        Args:
            parallel: If True, run all agents concurrently (faster but uses more resources)
                      If False, run sequentially in priority order
        """
        self.log.info("orchestrator_run_all_starting", parallel=parallel)
        results: dict[str, AgentResult] = {}

        # Priority order: SoD first (security), then lifecycle, then certification, mining, then dev
        agent_order = ["sod_detector", "lifecycle", "certification", "role_miner", "dev_agent"]

        if parallel:
            tasks = {
                name: asyncio.create_task(self.run_agent(name))
                for name in agent_order
            }
            for name, task in tasks.items():
                result = await task
                if result:
                    results[name] = result
        else:
            for name in agent_order:
                result = await self.run_agent(name)
                if result:
                    results[name] = result

        self._log_summary(results)
        return results

    async def run_dev_cycle(self) -> AgentResult | None:
        """Trigger one autonomous development cycle — scan, code, test, commit, push."""
        self.log.info("dev_cycle_triggered")
        return await self.run_agent("dev_agent")

    async def run_emergency_sod_scan(self) -> AgentResult | None:
        """Trigger an immediate SoD scan (e.g., after a new role assignment)."""
        self.log.warning("emergency_sod_scan_triggered")
        return await self.run_agent("sod_detector")

    async def run_lifecycle_flush(self) -> AgentResult | None:
        """Process all pending lifecycle events immediately."""
        self.log.info("lifecycle_flush_triggered")
        return await self.run_agent("lifecycle")

    def get_status(self) -> dict[str, Any]:
        """Return current status of all agents."""
        return {
            "agents": list(self.agents.keys()),
            "dry_run": settings.agent_dry_run,
            "model": settings.agent_model,
            "recent_runs": self.run_history[-10:],  # Last 10 runs
            "total_runs": len(self.run_history),
            "timestamp": datetime.utcnow().isoformat(),
        }

    def _record_run(self, agent_name: str, result: AgentResult) -> None:
        self.run_history.append(
            {
                "agent": agent_name,
                "timestamp": datetime.utcnow().isoformat(),
                "success": result.success,
                "items_processed": result.items_processed,
                "items_actioned": result.items_actioned,
                "errors": result.errors,
                "duration_seconds": result.duration_seconds,
                "dry_run": result.dry_run,
            }
        )
        # Keep last 1000 records
        if len(self.run_history) > 1000:
            self.run_history = self.run_history[-1000:]

    def _log_summary(self, results: dict[str, AgentResult]) -> None:
        total_processed = sum(r.items_processed for r in results.values())
        total_actioned = sum(r.items_actioned for r in results.values())
        total_errors = sum(len(r.errors) for r in results.values())
        successes = sum(1 for r in results.values() if r.success)

        self.log.info(
            "orchestrator_run_complete",
            agents_run=len(results),
            agents_succeeded=successes,
            total_items_processed=total_processed,
            total_items_actioned=total_actioned,
            total_errors=total_errors,
        )


# Singleton orchestrator instance
orchestrator = AgentOrchestrator()
