"""Stateful check-in agent."""

import logging
from typing import Any

from app.agents.base import Agent

logger = logging.getLogger(__name__)


class CheckinAgent(Agent):
    """Generate patient check-ins after non-adherence."""

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return check-in recommendation with state-sensitive logic."""
        consecutive_misses = int(payload.get("consecutive_misses", 0))
        risk = "high" if consecutive_misses >= 3 else "medium" if consecutive_misses >= 2 else "low"
        logger.info(
            "agent.checkin.completed user_id=%s dose_log_id=%s consecutive_misses=%s risk_level=%s",
            payload.get("user_id"),
            payload.get("dose_log_id"),
            consecutive_misses,
            risk,
        )
        return {
            "status": "ok",
            "risk_level": risk,
            "message": "We noticed missed doses. Are you facing side-effects or schedule issues?",
            "confidence": 0.82,
        }
