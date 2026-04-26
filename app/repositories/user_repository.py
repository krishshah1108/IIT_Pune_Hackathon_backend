"""User repository."""

from datetime import datetime, timezone
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.base import BaseRepository
from app.utils.ids import new_id


class UserRepository(BaseRepository):
    """Mongo operations for users."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db.users)

    async def get_by_email(self, email: str) -> dict | None:
        """Fetch user by email."""
        return await self.collection.find_one({"email": email, "deleted_at": None})

    async def get_by_id(self, user_id: str) -> dict | None:
        """Fetch user by primary id."""
        return await self.collection.find_one({"_id": user_id, "deleted_at": None})

    async def create_user(self, email: str) -> dict:
        """Create a new user."""
        now = datetime.now(timezone.utc)
        document = {
            "_id": new_id("usr"),
            "email": email,
            "first_name": "",
            "last_name": "",
            "is_active": True,
            "caregiver_email": None,
            "preferred_language": "en",
            "last_login_at": now,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        await self.collection.insert_one(document)
        return document

    async def touch_login(self, user_id: str) -> None:
        """Update last login timestamp."""
        now = datetime.now(timezone.utc)
        await self.collection.update_one(
            {"_id": user_id},
            {"$set": {"last_login_at": now, "updated_at": now}},
        )

    async def update_profile(
        self,
        email: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict | None:
        """Set name fields present in the request (PATCH). Returns updated doc or None if not found."""
        user = await self.get_by_email(email)
        if not user:
            return None
        if first_name is None and last_name is None:
            return user
        now = datetime.now(timezone.utc)
        set_doc: dict = {"updated_at": now}
        if first_name is not None:
            set_doc["first_name"] = first_name
        if last_name is not None:
            set_doc["last_name"] = last_name
        await self.collection.update_one({"_id": user["_id"]}, {"$set": set_doc})
        return await self.get_by_email(email)

    async def update_profile_by_id(
        self,
        user_id: str,
        *,
        first_name: str | None = None,
        last_name: str | None = None,
    ) -> dict | None:
        """PATCH name fields by user id (JWT subject)."""
        user = await self.get_by_id(user_id)
        if not user:
            return None
        if first_name is None and last_name is None:
            return user
        now = datetime.now(timezone.utc)
        set_doc: dict = {"updated_at": now}
        if first_name is not None:
            set_doc["first_name"] = first_name
        if last_name is not None:
            set_doc["last_name"] = last_name
        await self.collection.update_one({"_id": user_id}, {"$set": set_doc})
        return await self.get_by_id(user_id)
