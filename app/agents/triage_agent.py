"""Clinical triage agent for escalation decisions."""

import logging
from typing import Any

from app.agents.base import Agent

logger = logging.getLogger(__name__)


class TriageAgent(Agent):
    """Classify risk and decide caregiver escalation."""

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return escalation decision."""
        risk_level = payload.get("risk_level", "low")
        escalate = risk_level == "high"
        logger.info("agent.triage.completed risk_level=%s escalate=%s", risk_level, escalate)
        return {
            "status": "ok",
            "escalate": escalate,
            "severity": "critical" if escalate else "warning",
            "confidence": 0.88 if escalate else 0.76,
        }
