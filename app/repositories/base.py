"""Base repository."""

from datetime import datetime, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorCollection


class BaseRepository:
    """Shared repository functionality."""

    def __init__(self, collection: AsyncIOMotorCollection):
        self.collection = collection

    @staticmethod
    def now() -> datetime:
        """Return UTC now."""
        return datetime.now(timezone.utc)

    async def insert_one(self, payload: dict[str, Any]) -> str:
        """Insert document and return id."""
        result = await self.collection.insert_one(payload)
        return str(result.inserted_id)
