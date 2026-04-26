"""Clinical triage agent for escalation decisions."""

import logging
from typing import Any

from app.agents.base import Agent

logger = logging.getLogger(__name__)


class TriageAgent(Agent):
    """Classify risk and decide caregiver escalation."""

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return escalation decision."""
        risk_level = str(payload.get("risk_level", "low")).lower().strip()
        dose_status = str(payload.get("status", "")).lower().strip()
        consecutive_misses = int(payload.get("consecutive_misses", 0))

        # Escalate for explicit user non-adherence actions and sustained high risk.
        escalate = dose_status in {"skipped", "missed"} or risk_level == "high" or consecutive_misses >= 3
        logger.info(
            "agent.triage.completed risk_level=%s status=%s consecutive_misses=%s escalate=%s",
            risk_level,
            dose_status or "unknown",
            consecutive_misses,
            escalate,
        )
        return {
            "status": "ok",
            "escalate": escalate,
            "severity": "critical" if escalate else "warning",
            "confidence": 0.88 if escalate else 0.76,
        }
