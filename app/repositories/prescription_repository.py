"""Prescription repository."""

from datetime import datetime, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.base import BaseRepository
from app.utils.ids import new_id


class PrescriptionRepository(BaseRepository):
    """Mongo operations for prescriptions."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db.prescriptions)

    async def create(
        self,
        user_id: str,
        image_hash: str,
        language: str,
        image_url: str,
        cloudinary_public_id: str,
    ) -> dict[str, Any]:
        """Create prescription upload document."""
        now = datetime.now(timezone.utc)
        doc = {
            "_id": new_id("prx"),
            "user_id": user_id,
            "content_hash": image_hash,
            "language": language,
            "image_url": image_url,
            "cloudinary_public_id": cloudinary_public_id,
            "status": "uploaded",
            "ai_output": {},
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        await self.collection.insert_one(doc)
        return doc

    async def find_duplicate(self, user_id: str, image_hash: str) -> dict | None:
        """Find duplicate upload only when an identical prescription is already confirmed."""
        return await self.collection.find_one(
            {
                "user_id": user_id,
                "content_hash": image_hash,
                "status": "confirmed",
                "deleted_at": None,
            }
        )

    async def update_status(self, prescription_id: str, status: str, ai_output: dict[str, Any] | None = None) -> None:
        """Update processing status and optional AI payload."""
        payload: dict[str, Any] = {"status": status, "updated_at": datetime.now(timezone.utc)}
        if ai_output is not None:
            payload["ai_output"] = ai_output
        await self.collection.update_one({"_id": prescription_id}, {"$set": payload})

    async def get_by_id(self, prescription_id: str) -> dict | None:
        """Fetch prescription by id."""
        return await self.collection.find_one({"_id": prescription_id, "deleted_at": None})

    async def get_owned(self, prescription_id: str, user_id: str) -> dict | None:
        """Fetch prescription if it belongs to user_id."""
        return await self.collection.find_one(
            {"_id": prescription_id, "user_id": user_id, "deleted_at": None},
        )

    async def delete_owned(self, prescription_id: str, user_id: str) -> bool:
        """Hard-delete a prescription row if owned by user."""
        result = await self.collection.delete_one({"_id": prescription_id, "user_id": user_id})
        return result.deleted_count == 1

    async def apply_demo_upload_draft(
        self,
        prescription_id: str,
        user_id: str,
        *,
        image_url: str,
        cloudinary_public_id: str,
        content_hash: str,
        language: str,
        ai_output: dict[str, Any],
    ) -> bool:
        """Set prescription to awaiting_confirmation with canned AI (demo mode)."""
        result = await self.collection.update_one(
            {"_id": prescription_id, "user_id": user_id, "deleted_at": None},
            {
                "$set": {
                    "status": "awaiting_confirmation",
                    "image_url": image_url,
                    "cloudinary_public_id": cloudinary_public_id,
                    "content_hash": content_hash,
                    "language": language,
                    "ai_output": ai_output,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.matched_count == 1
