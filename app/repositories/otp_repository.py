"""OTP session repository."""

from datetime import datetime, timedelta, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.base import BaseRepository
from app.utils.ids import new_id


class OTPRepository(BaseRepository):
    """Mongo operations for OTP sessions."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db.otp_sessions)

    async def count_recent_requests(self, email: str, window_hours: int = 1) -> int:
        """Count OTP requests in time window."""
        threshold = datetime.now(timezone.utc) - timedelta(hours=window_hours)
        return await self.collection.count_documents({"email": email, "created_at": {"$gte": threshold}})

    async def get_latest(self, email: str) -> dict | None:
        """Get latest OTP session."""
        return await self.collection.find_one({"email": email}, sort=[("created_at", -1)])

    async def create_session(self, email: str, otp_hash: str, expires_at: datetime) -> dict:
        """Create OTP session row."""
        now = datetime.now(timezone.utc)
        doc = {
            "_id": new_id("otp"),
            "email": email,
            "otp_hash": otp_hash,
            "attempts": 0,
            "verified": False,
            "expires_at": expires_at,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        await self.collection.insert_one(doc)
        return doc

    async def mark_attempt(self, session_id: str) -> None:
        """Increment attempts."""
        await self.collection.update_one(
            {"_id": session_id},
            {"$inc": {"attempts": 1}, "$set": {"updated_at": datetime.now(timezone.utc)}},
        )

    async def mark_verified(self, session_id: str) -> None:
        """Mark OTP as verified."""
        await self.collection.update_one(
            {"_id": session_id},
            {"$set": {"verified": True, "updated_at": datetime.now(timezone.utc)}},
        )
