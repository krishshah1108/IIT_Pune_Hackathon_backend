"""Base agent protocol."""

from abc import ABC, abstractmethod
from typing import Any


class Agent(ABC):
    """Abstract AI agent contract."""

    @abstractmethod
    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Execute agent and return structured JSON."""
