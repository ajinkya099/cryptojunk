"""Base AI agent class — all AISm agents inherit from this."""

from __future__ import annotations

import json
import time
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from typing import Any

import structlog
from anthropic import AsyncAnthropic
from tenacity import retry, stop_after_attempt, wait_exponential

from iga.config import settings

logger = structlog.get_logger(__name__)


@dataclass
class AgentDecision:
    """Structured result from an AI agent decision."""

    action: str                    # What the agent decided to do
    reasoning: str                 # Why the agent made this decision
    confidence: float              # 0.0 - 1.0
    data: dict[str, Any] = field(default_factory=dict)  # Additional structured data
    requires_human_review: bool = False
    risk_level: str = "low"        # low | medium | high | critical
    timestamp: datetime = field(default_factory=datetime.utcnow)

    def is_high_confidence(self, threshold: float | None = None) -> bool:
        threshold = threshold or settings.agent_confidence_threshold
        return self.confidence >= threshold

    def to_dict(self) -> dict[str, Any]:
        return {
            "action": self.action,
            "reasoning": self.reasoning,
            "confidence": self.confidence,
            "data": self.data,
            "requires_human_review": self.requires_human_review,
            "risk_level": self.risk_level,
            "timestamp": self.timestamp.isoformat(),
        }


@dataclass
class AgentResult:
    """Result of an agent run cycle."""

    agent_name: str
    success: bool
    decisions: list[AgentDecision] = field(default_factory=list)
    items_processed: int = 0
    items_actioned: int = 0
    errors: list[str] = field(default_factory=list)
    duration_seconds: float = 0.0
    dry_run: bool = True

    def summary(self) -> str:
        status = "SUCCESS" if self.success else "FAILED"
        return (
            f"[{self.agent_name}] {status} | "
            f"processed={self.items_processed} actioned={self.items_actioned} "
            f"errors={len(self.errors)} duration={self.duration_seconds:.1f}s "
            f"dry_run={self.dry_run}"
        )


class BaseAgent(ABC):
    """
    Base class for all AISm autonomous agents.

    Each agent:
    - Has a Claude-powered decision-making engine
    - Logs all decisions with full reasoning traces
    - Respects dry_run mode (logs but doesn't execute)
    - Uses retry logic for API calls
    - Reports metrics for monitoring
    """

    def __init__(self, name: str, description: str) -> None:
        self.name = name
        self.description = description
        self.client = AsyncAnthropic(api_key=settings.anthropic_api_key)
        self.model = settings.agent_model
        self.max_tokens = settings.agent_max_tokens
        self.dry_run = settings.agent_dry_run
        self.log = structlog.get_logger(f"agent.{name}")

    @abstractmethod
    async def run(self) -> AgentResult:
        """Execute the agent's main logic. Must be implemented by subclasses."""

    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=2, max=10),
        reraise=True,
    )
    async def ask_claude(
        self,
        system_prompt: str,
        user_message: str,
        expect_json: bool = True,
    ) -> str:
        """
        Send a prompt to Claude and return the response text.

        Args:
            system_prompt: The system prompt defining agent behavior
            user_message: The specific question/task for this call
            expect_json: If True, instruct Claude to return valid JSON

        Returns:
            Raw response text from Claude
        """
        if expect_json:
            user_message = (
                f"{user_message}\n\nRespond with valid JSON only. "
                "No markdown code blocks. No explanatory text outside the JSON."
            )

        response = await self.client.messages.create(
            model=self.model,
            max_tokens=self.max_tokens,
            system=system_prompt,
            messages=[{"role": "user", "content": user_message}],
        )
        return response.content[0].text  # type: ignore[union-attr]

    async def make_decision(
        self,
        system_prompt: str,
        context: dict[str, Any],
        decision_schema: str = "",
    ) -> AgentDecision:
        """
        Ask Claude to make a structured decision given context.

        Returns an AgentDecision with action, reasoning, and confidence.
        """
        schema_hint = decision_schema or (
            '{"action": "string", "reasoning": "string", '
            '"confidence": 0.0-1.0, "requires_human_review": bool, '
            '"risk_level": "low|medium|high|critical", "data": {}}'
        )

        user_message = (
            f"Context:\n{json.dumps(context, indent=2, default=str)}\n\n"
            f"Make a decision. Return JSON matching this schema:\n{schema_hint}"
        )

        raw = await self.ask_claude(system_prompt, user_message, expect_json=True)

        try:
            parsed = json.loads(raw)
            return AgentDecision(
                action=parsed.get("action", "no_action"),
                reasoning=parsed.get("reasoning", ""),
                confidence=float(parsed.get("confidence", 0.5)),
                data=parsed.get("data", {}),
                requires_human_review=parsed.get("requires_human_review", False),
                risk_level=parsed.get("risk_level", "low"),
            )
        except (json.JSONDecodeError, KeyError, ValueError) as e:
            self.log.error("failed_to_parse_decision", raw=raw, error=str(e))
            return AgentDecision(
                action="error",
                reasoning=f"Failed to parse AI response: {e}. Raw: {raw[:200]}",
                confidence=0.0,
                requires_human_review=True,
                risk_level="high",
            )

    def _start_run(self) -> float:
        self.log.info("agent_starting", agent=self.name, dry_run=self.dry_run)
        return time.time()

    def _end_run(self, result: AgentResult, start_time: float) -> AgentResult:
        result.duration_seconds = time.time() - start_time
        self.log.info(
            "agent_completed",
            summary=result.summary(),
            dry_run=self.dry_run,
        )
        return result

    def _log_decision(self, decision: AgentDecision, context_id: str = "") -> None:
        self.log.info(
            "agent_decision",
            agent=self.name,
            context_id=context_id,
            action=decision.action,
            confidence=decision.confidence,
            risk_level=decision.risk_level,
            requires_human_review=decision.requires_human_review,
            reasoning_preview=decision.reasoning[:200] if decision.reasoning else "",
            dry_run=self.dry_run,
        )
