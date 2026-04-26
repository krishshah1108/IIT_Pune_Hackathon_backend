"""Dose log repository."""

from datetime import datetime, timezone
from typing import Any
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.base import BaseRepository
from app.utils.ids import new_id


class DoseLogRepository(BaseRepository):
    """Mongo operations for dose logs."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db.dose_logs)

    async def bulk_create(self, user_id: str, medicine_id: str, schedule: list[datetime]) -> list[str]:
        """Create dose log entries from schedule timestamps."""
        now = datetime.now(timezone.utc)
        docs: list[dict[str, Any]] = []
        for scheduled_for in schedule:
            docs.append(
                {
                    "_id": new_id("dose"),
                    "user_id": user_id,
                    "medicine_id": medicine_id,
                    "scheduled_for": scheduled_for,
                    "status": "pending",
                    "taken_at": None,
                    "created_at": now,
                    "updated_at": now,
                    "deleted_at": None,
                }
            )
        if docs:
            await self.collection.insert_many(docs)
        return [doc["_id"] for doc in docs]

    async def update_status(self, dose_log_id: str, status: str, taken_at: datetime | None) -> bool:
        """Mark dose as taken/missed/skipped."""
        result = await self.collection.update_one(
            {"_id": dose_log_id, "deleted_at": None, "status": "pending"},
            {
                "$set": {
                    "status": status,
                    "taken_at": taken_at,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0

    async def update_status_for_user(
        self,
        dose_log_id: str,
        user_id: str,
        status: str,
        taken_at: datetime | None,
    ) -> bool:
        """Mark dose only if it belongs to the given user."""
        result = await self.collection.update_one(
            {"_id": dose_log_id, "user_id": user_id, "deleted_at": None, "status": "pending"},
            {
                "$set": {
                    "status": status,
                    "taken_at": taken_at,
                    "updated_at": datetime.now(timezone.utc),
                }
            },
        )
        return result.modified_count > 0

    async def get_by_id_for_user(self, dose_log_id: str, user_id: str) -> dict | None:
        """Fetch one dose log by id for owner."""
        return await self.collection.find_one({"_id": dose_log_id, "user_id": user_id, "deleted_at": None})

    async def count_consecutive_nonadherence(
        self,
        user_id: str,
        medicine_id: str,
        upto_scheduled_for: datetime,
    ) -> int:
        """Count consecutive missed/skipped doses backwards from latest slot."""
        cursor = (
            self.collection.find(
                {
                    "user_id": user_id,
                    "medicine_id": medicine_id,
                    "scheduled_for": {"$lte": upto_scheduled_for},
                    "deleted_at": None,
                }
            )
            .sort("scheduled_for", -1)
            .limit(100)
        )
        count = 0
        async for row in cursor:
            st = str(row.get("status", "")).strip().lower()
            if st in {"missed", "skipped"}:
                count += 1
                continue
            break
        return count

    async def get_due_missed(self, threshold: datetime) -> list[dict]:
        """Fetch pending doses past threshold."""
        cursor = self.collection.find(
            {
                "status": "pending",
                "scheduled_for": {"$lt": threshold},
                "deleted_at": None,
            }
        )
        return [doc async for doc in cursor]

    async def mark_missed(self, dose_log_id: str) -> None:
        """Set dose as missed if still pending."""
        await self.collection.update_one(
            {"_id": dose_log_id, "status": "pending"},
            {"$set": {"status": "missed", "updated_at": datetime.now(timezone.utc)}},
        )

    async def list_for_user_between(self, user_id: str, start_utc: datetime, end_utc: datetime) -> list[dict]:
        """List dose logs for user in [start_utc, end_utc)."""
        cursor = (
            self.collection.find(
                {
                    "user_id": user_id,
                    "deleted_at": None,
                    "scheduled_for": {"$gte": start_utc, "$lt": end_utc},
                }
            )
            .sort("scheduled_for", 1)
        )
        return [doc async for doc in cursor]

    async def list_detailed_for_user_between(self, user_id: str, start_utc: datetime, end_utc: datetime) -> list[dict]:
        """List dose logs with medicine names for user in [start_utc, end_utc)."""
        pipeline = [
            {
                "$match": {
                    "user_id": user_id,
                    "deleted_at": None,
                    "scheduled_for": {"$gte": start_utc, "$lt": end_utc},
                }
            },
            {
                "$lookup": {
                    "from": "medicines",
                    "let": {"med_id": "$medicine_id", "u_id": "$user_id"},
                    "pipeline": [
                        {
                            "$match": {
                                "$expr": {
                                    "$and": [
                                        {"$eq": ["$_id", "$$med_id"]},
                                        {"$eq": ["$user_id", "$$u_id"]},
                                        {"$eq": ["$deleted_at", None]},
                                    ]
                                }
                            }
                        },
                        {"$project": {"_id": 0, "name": 1}},
                    ],
                    "as": "medicine_docs",
                }
            },
            {
                "$project": {
                    "_id": 1,
                    "medicine_id": 1,
                    "scheduled_for": 1,
                    "status": 1,
                    "taken_at": 1,
                    "medicine_name": {"$ifNull": [{"$first": "$medicine_docs.name"}, "Unknown medicine"]},
                }
            },
            {"$sort": {"scheduled_for": 1}},
        ]
        cursor = self.collection.aggregate(pipeline)
        return [doc async for doc in cursor]
