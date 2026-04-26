"""Medicine repository."""

from datetime import datetime, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.base import BaseRepository
from app.utils.ids import new_id


class MedicineRepository(BaseRepository):
    """Mongo operations for medicines."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db.medicines)

    async def bulk_create(self, prescription_id: str, user_id: str, medicines: list[dict[str, Any]]) -> list[str]:
        """Insert extracted medicines."""
        now = datetime.now(timezone.utc)
        docs = []
        for med in medicines:
            docs.append(
                {
                    "_id": new_id("med"),
                    "prescription_id": prescription_id,
                    "user_id": user_id,
                    **med,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
            )
        if docs:
            await self.collection.insert_many(docs)
        return [doc["_id"] for doc in docs]

    async def list_by_prescription(self, prescription_id: str) -> list[dict]:
        """List medicines attached to a prescription."""
        cursor = self.collection.find({"prescription_id": prescription_id, "deleted_at": None})
        return [doc async for doc in cursor]

    async def list_by_user(self, user_id: str, prescription_id: str | None = None) -> list[dict]:
        """List medicines for a user, optionally scoped to one prescription."""
        query: dict[str, Any] = {"user_id": user_id, "deleted_at": None}
        if prescription_id:
            query["prescription_id"] = prescription_id
        cursor = self.collection.find(query).sort("created_at", -1)
        return [doc async for doc in cursor]

    async def hard_delete_for_prescription(self, prescription_id: str, user_id: str) -> int:
        """Remove all medicine rows for a prescription (demo reset / admin)."""
        result = await self.collection.delete_many({"prescription_id": prescription_id, "user_id": user_id})
        return int(result.deleted_count)
