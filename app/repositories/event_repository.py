"""Event repository for idempotency."""

from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase
from pymongo.errors import DuplicateKeyError


class EventRepository:
    """Store processed events for idempotency."""

    def __init__(self, db: AsyncIOMotorDatabase):
        self.collection = db.events

    async def register_event(self, event_id: str, event_type: str, payload: dict) -> bool:
        """Insert event if unseen; return False for duplicates."""
        now = datetime.now(timezone.utc)
        try:
            await self.collection.insert_one(
                {
                    "_id": event_id,
                    "event_type": event_type,
                    "payload": payload,
                    "status": "processed",
                    "created_at": now,
                    "updated_at": now,
                }
            )
            return True
        except DuplicateKeyError:
            return False
