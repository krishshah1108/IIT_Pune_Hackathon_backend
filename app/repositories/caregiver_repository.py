"""Caregiver repository — multiple caregivers per patient (user)."""

from datetime import datetime, timezone
from typing import Any

from motor.motor_asyncio import AsyncIOMotorDatabase

from app.repositories.base import BaseRepository
from app.utils.ids import new_id


def _norm_email(email: str) -> str:
    return email.strip().lower()


class CaregiverRepository(BaseRepository):
    """Mongo `caregivers` collection: owned by `user_id` (JWT `sub`)."""

    def __init__(self, db: AsyncIOMotorDatabase):
        super().__init__(db.caregivers)

    async def list_by_user(
        self,
        user_id: str,
        *,
        include_inactive: bool = False,
    ) -> list[dict[str, Any]]:
        """List caregivers for a patient. Excludes soft-deleted rows always."""
        q: dict[str, Any] = {"user_id": user_id, "deleted_at": None}
        if not include_inactive:
            q["is_active"] = True
        cursor = self.collection.find(q).sort("created_at", 1)
        return await cursor.to_list(length=500)

    async def get_by_id(self, caregiver_id: str, user_id: str) -> dict | None:
        """Single caregiver; must belong to `user_id` and not be soft-deleted."""
        return await self.collection.find_one(
            {"_id": caregiver_id, "user_id": user_id, "deleted_at": None},
        )

    async def email_taken(
        self,
        user_id: str,
        email: str,
        *,
        except_id: str | None = None,
    ) -> bool:
        """Another non-deleted caregiver for this user already has this email."""
        n = _norm_email(email)
        q: dict[str, Any] = {
            "user_id": user_id,
            "email": n,
            "deleted_at": None,
        }
        if except_id is not None:
            q["_id"] = {"$ne": except_id}
        doc = await self.collection.find_one(q)
        return doc is not None

    async def create(
        self,
        user_id: str,
        *,
        display_name: str,
        email: str,
        phone: str | None = None,
        relationship_label: str | None = None,
        is_active: bool = True,
        notify_on_missed_dose: bool = True,
    ) -> dict[str, Any]:
        now = datetime.now(timezone.utc)
        n_email = _norm_email(email)
        document: dict[str, Any] = {
            "_id": new_id("cgr"),
            "user_id": user_id,
            "display_name": display_name.strip()[:200],
            "email": n_email,
            "phone": (phone.strip()[:32] if phone and phone.strip() else None),
            "relationship_label": (
                relationship_label.strip()[:80] if relationship_label and relationship_label.strip() else None
            ),
            "is_active": is_active,
            "notify_on_missed_dose": notify_on_missed_dose,
            "created_at": now,
            "updated_at": now,
            "deleted_at": None,
        }
        await self.collection.insert_one(document)
        return document

    async def update(
        self,
        caregiver_id: str,
        user_id: str,
        patch: dict[str, Any],
    ) -> dict | None:
        """Partial update from a non-empty set of fields (e.g. `body.model_dump(exclude_unset=True)`). Returns None if not found."""
        existing = await self.get_by_id(caregiver_id, user_id)
        if not existing:
            return None
        set_doc: dict[str, Any] = {"updated_at": datetime.now(timezone.utc)}
        if "display_name" in patch:
            set_doc["display_name"] = str(patch["display_name"]).strip()[:200]
        if "email" in patch:
            set_doc["email"] = _norm_email(str(patch["email"]))
        if "phone" in patch:
            s = patch["phone"]
            if s is None or (isinstance(s, str) and not s.strip()):
                set_doc["phone"] = None
            else:
                set_doc["phone"] = str(s).strip()[:32]
        if "relationship_label" in patch:
            s = patch.get("relationship_label")
            if s is None or (isinstance(s, str) and not s.strip()):
                set_doc["relationship_label"] = None
            else:
                set_doc["relationship_label"] = str(s).strip()[:80]
        if "is_active" in patch:
            set_doc["is_active"] = bool(patch["is_active"])
        if "notify_on_missed_dose" in patch:
            set_doc["notify_on_missed_dose"] = bool(patch["notify_on_missed_dose"])
        if len(set_doc) <= 1:
            return existing
        await self.collection.update_one(
            {"_id": caregiver_id, "user_id": user_id, "deleted_at": None},
            {"$set": set_doc},
        )
        return await self.get_by_id(caregiver_id, user_id)

    async def soft_delete(self, caregiver_id: str, user_id: str) -> bool:
        """Logical delete. Returns True if a document was updated."""
        now = datetime.now(timezone.utc)
        result = await self.collection.update_one(
            {"_id": caregiver_id, "user_id": user_id, "deleted_at": None},
            {"$set": {"deleted_at": now, "updated_at": now, "is_active": False}},
        )
        return result.modified_count == 1
