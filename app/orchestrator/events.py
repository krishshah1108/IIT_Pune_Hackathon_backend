"""Domain events."""

from datetime import datetime, timezone
from typing import Any
from pydantic import BaseModel, Field

from app.utils.ids import new_id


class Event(BaseModel):
    """Event model used across orchestrator."""

    event_id: str = Field(default_factory=lambda: new_id("evt"))
    event_type: str
    payload: dict[str, Any]
    created_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
