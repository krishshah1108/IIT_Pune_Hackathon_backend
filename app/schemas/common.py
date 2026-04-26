"""Shared request/response schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class APIResponse(BaseModel):
    """Generic API response wrapper."""

    success: bool = True
    message: str = "ok"


class TimestampedResponse(APIResponse):
    """Response with timestamp for client sync."""

    timestamp: datetime = Field(default_factory=datetime.utcnow)
