"""Shared model types."""

from datetime import datetime
from typing import Any
from pydantic import BaseModel, ConfigDict, Field


class MongoModel(BaseModel):
    """Base model for MongoDB documents."""

    id: str | None = Field(default=None, alias="_id")
    created_at: datetime
    updated_at: datetime
    deleted_at: datetime | None = None

    model_config = ConfigDict(populate_by_name=True, arbitrary_types_allowed=True)


class EventRecord(MongoModel):
    """Persisted event for idempotency and replay safety."""

    event_type: str
    payload: dict[str, Any]
    status: str = "processed"
