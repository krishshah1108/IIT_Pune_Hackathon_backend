"""Alert repository."""

from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.base import BaseRepository
from app.utils.ids import new_id


class AlertRepository(BaseRepository):
    """Mongo operations for caregiver alerts."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db.alerts)

    async def create_alert(self, user_id: str, severity: str, message: str) -> dict:
        """Create alert document."""
        now = datetime.now(timezone.utc)
        doc = {
            "_id": new_id("alt"),
            "user_id": user_id,
            "severity": severity,
            "message": message,
            "status": "queued",
            "delivery_channel": "email",
            "delivery_status": "queued",
            "failure_reason": None,
            "sent_at": None,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        await self.collection.insert_one(doc)
        return doc

    async def mark_sent(self, alert_id: str) -> None:
        """Mark alert as sent."""
        now = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"_id": alert_id},
            {
                "$set": {
                    "status": "sent",
                    "delivery_status": "sent",
                    "failure_reason": None,
                    "sent_at": now,
                    "updated_at": now,
                }
            },
        )

    async def mark_failed(self, alert_id: str, reason: str) -> None:
        """Mark alert as failed with reason."""
        await self.collection.update_one(
            {"_id": alert_id},
            {
                "$set": {
                    "status": "failed",
                    "delivery_status": "failed",
                    "failure_reason": reason[:500],
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )

    async def list_by_user(self, user_id: str, *, limit: int = 50) -> list[dict]:
        """Fetch recent alerts for a user."""
        cursor = self.collection.find({"user_id": user_id, "deleted_at": None}).sort("created_at", -1).limit(max(1, min(limit, 200)))
        return [doc async for doc in cursor]
