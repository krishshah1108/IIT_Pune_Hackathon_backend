"""Prescription service."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.core.demo_prescriptions import build_demo_ai_output
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.repositories.dose_log_repository import DoseLogRepository
from app.repositories.medicine_repository import MedicineRepository
from app.repositories.prescription_repository import PrescriptionRepository
from app.repositories.user_repository import UserRepository
from app.services.cloudinary_service import CloudinaryService
from app.services.schedule_service import ScheduleService
from app.utils.normalization import hash_bytes, normalize_dosage_pattern, normalize_medicine_name, parse_frequency
from app.utils.reminder_times import coerce_reminder_times_24h

logger = logging.getLogger(__name__)


class PrescriptionService:
    """Handle prescription upload, AI draft, and user-confirmed commit."""

    def __init__(
        self,
        prescription_repo: PrescriptionRepository,
        medicine_repo: MedicineRepository,
        user_repo: UserRepository,
        cloudinary: CloudinaryService,
        dose_repo: DoseLogRepository,
        schedule_service: ScheduleService,
    ):
        self.prescription_repo = prescription_repo
        self.medicine_repo = medicine_repo
        self.user_repo = user_repo
        self.cloudinary = cloudinary
        self.dose_repo = dose_repo
        self.schedule_service = schedule_service

    async def create_upload_from_file(
        self,
        user_id: str,
        file_bytes: bytes,
        content_type: str,
        original_filename: str | None,
        language: str,
    ) -> dict:
        """Upload image to Cloudinary and create prescription record; reject duplicates."""
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        self.cloudinary.validate_content_type(content_type)
        image_hash = hash_bytes(file_bytes)
        duplicate = await self.prescription_repo.find_duplicate(user["_id"], image_hash)
        if duplicate:
            raise ConflictError("Duplicate confirmed prescription upload detected")

        safe_name = (original_filename or "prescription").replace("\\", "/").split("/")[-1][:120]
        upload_meta = await self.cloudinary.upload_prescription_image(file_bytes, safe_name)
        return await self.prescription_repo.create(
            user_id=user["_id"],
            image_hash=image_hash,
            language=language,
            image_url=upload_meta["secure_url"],
            cloudinary_public_id=upload_meta["public_id"],
        )

    async def apply_demo_prescription_upload(
        self,
        user_id: str,
        demo_prescription_id: str,
        file_bytes: bytes,
        content_type: str,
        original_filename: str | None,
        language: str,
    ) -> dict[str, Any]:
        """
        Demo mode: reuse a fixed prx_* row, upload a new image to Cloudinary, attach canned AI draft.
        Skips Gemini; confirm/update flows use the same prescription id as production.
        """
        user = await self.user_repo.get_by_id(user_id)
        if not user:
            raise NotFoundError("User not found")

        self.cloudinary.validate_content_type(content_type)
        image_hash = hash_bytes(file_bytes)

        doc = await self.prescription_repo.get_owned(demo_prescription_id, user_id)
        if not doc:
            raise NotFoundError(
                "Demo prescription not found for this account. Insert the prx_* document for this user in MongoDB."
            )

        safe_name = (original_filename or "prescription").replace("\\", "/").split("/")[-1][:120]
        upload_meta = await self.cloudinary.upload_prescription_image(file_bytes, safe_name)
        new_public_id = str(upload_meta["public_id"])
        new_url = str(upload_meta["secure_url"])

        old_public_id = str(doc.get("cloudinary_public_id") or "").strip()
        if old_public_id and old_public_id != new_public_id:
            try:
                await self.cloudinary.delete_prescription_image(old_public_id)
            except Exception as exc:
                logger.warning(
                    "prescription.demo.cloudinary_delete_failed prescription_id=%s user_id=%s error=%s",
                    demo_prescription_id,
                    user_id,
                    str(exc),
                )

        if doc.get("status") == "confirmed":
            med_rows = await self.medicine_repo.list_by_prescription(demo_prescription_id)
            med_ids = [str(m["_id"]) for m in med_rows]
            if med_ids:
                await self.dose_repo.hard_delete_for_medicines(user_id, med_ids)
            await self.medicine_repo.hard_delete_for_prescription(demo_prescription_id, user_id)

        ai_out = build_demo_ai_output(language, demo_prescription_id)
        ok = await self.prescription_repo.apply_demo_upload_draft(
            demo_prescription_id,
            user_id,
            image_url=new_url,
            cloudinary_public_id=new_public_id,
            content_hash=image_hash,
            language=language,
            ai_output=ai_out,
        )
        if not ok:
            raise NotFoundError("Could not update demo prescription (wrong owner or missing row).")

        updated = await self.prescription_repo.get_owned(demo_prescription_id, user_id)
        if not updated:
            raise NotFoundError("Prescription missing after demo update")
        logger.info(
            "prescription.demo_upload_done user_id=%s prescription_id=%s bytes=%s",
            user_id,
            demo_prescription_id,
            len(file_bytes),
        )
        return updated

    async def persist_medicines(self, prescription_id: str, user_id: str, medicines: list[dict]) -> list[str]:
        """Normalize and persist medicine entries."""
        normalized = []
        for med in medicines:
            if not med.get("name") or not med.get("dosage_pattern"):
                continue
            dose_pattern = normalize_dosage_pattern(med["dosage_pattern"])
            times = coerce_reminder_times_24h(med.get("reminder_times_24h"), dose_pattern)
            normalized.append(
                {
                    "name": med["name"],
                    "name_normalized": normalize_medicine_name(med["name"]),
                    "dosage_pattern": dose_pattern,
                    "frequency": parse_frequency(dose_pattern),
                    "duration_days": int(med.get("duration_days", 30)),
                    "instructions": med.get("instructions"),
                    "confidence": float(med.get("confidence", 0.7)),
                    "reminder_times_24h": times,
                }
            )
        return await self.medicine_repo.bulk_create(prescription_id, user_id, normalized)

    async def get_owned_prescription(self, user_id: str, prescription_id: str) -> dict[str, Any] | None:
        """Return raw prescription row for owner (e.g. after synchronous pipeline)."""
        return await self.prescription_repo.get_owned(prescription_id, user_id)

    async def discard_failed_upload(self, user_id: str, prescription_id: str) -> bool:
        """Remove failed upload row and its Cloudinary image."""
        doc = await self.prescription_repo.get_owned(prescription_id, user_id)
        if not doc:
            return False

        public_id = str(doc.get("cloudinary_public_id") or "").strip()
        if public_id:
            try:
                await self.cloudinary.delete_prescription_image(public_id)
            except Exception as exc:
                logger.warning(
                    "prescription.discard.cloudinary_delete_failed prescription_id=%s user_id=%s error=%s",
                    prescription_id,
                    user_id,
                    str(exc),
                )
        deleted = await self.prescription_repo.delete_owned(prescription_id, user_id)
        logger.info("prescription.discarded_failed_upload prescription_id=%s user_id=%s deleted=%s", prescription_id, user_id, deleted)
        return deleted

    async def confirm_prescription(
        self,
        user_id: str,
        prescription_id: str,
        medicines: list[dict[str, Any]] | None,
    ) -> dict[str, Any]:
        """
        Persist medicines and dose schedules after user confirms the AI draft.
        Idempotent: if already confirmed, returns current snapshot without duplicating rows.
        """
        doc = await self.prescription_repo.get_owned(prescription_id, user_id)
        if not doc:
            raise NotFoundError("Prescription not found")
        if doc["status"] == "confirmed":
            meds = await self._medicines_public(prescription_id)
            return {"prescription_id": prescription_id, "status": "confirmed", "medicines": meds, "idempotent": True}

        if doc["status"] != "awaiting_confirmation":
            raise ConflictError(f"Prescription cannot be confirmed in status: {doc['status']}")

        resolved = medicines
        if resolved is None:
            vision = (doc.get("ai_output") or {}).get("vision") or {}
            resolved = list(vision.get("medicines") or [])
        if not resolved:
            raise ValidationError("No medicines to confirm; provide medicines or complete AI extraction first.")

        med_rows: list[dict[str, Any]] = []
        for row in resolved:
            name = str(row.get("name", "")).strip()
            pattern = str(row.get("dosage_pattern", "")).strip()
            if not name or not pattern:
                continue
            canon = normalize_dosage_pattern(pattern)
            med_rows.append(
                {
                    "name": name,
                    "dosage_pattern": canon,
                    "duration_days": int(row.get("duration_days", 30)),
                    "instructions": row.get("instructions"),
                    "confidence": float(row.get("confidence", 0.75)),
                    "reminder_times_24h": coerce_reminder_times_24h(row.get("reminder_times_24h"), canon),
                }
            )
        if not med_rows:
            raise ValidationError("Each medicine needs a non-empty name and dosage_pattern.")

        medicine_ids = await self.persist_medicines(prescription_id, user_id, med_rows)
        for med_id, med in zip(medicine_ids, med_rows):
            schedule = self.schedule_service.generate_schedule(
                med["dosage_pattern"],
                int(med.get("duration_days", 30)),
                reminder_times_24h=med.get("reminder_times_24h"),
            )
            await self.dose_repo.bulk_create(user_id=user_id, medicine_id=med_id, schedule=schedule)

        ai_out = dict(doc.get("ai_output") or {})
        ai_out["confirmed_at"] = datetime.now(timezone.utc).isoformat()
        ai_out["medicine_ids"] = medicine_ids
        await self.prescription_repo.update_status(prescription_id, "confirmed", ai_out)

        public = await self._medicines_public(prescription_id)
        logger.info("prescription.confirmed prescription_id=%s user_id=%s medicines=%s", prescription_id, user_id, len(public))
        return {"prescription_id": prescription_id, "status": "confirmed", "medicines": public, "idempotent": False}

    async def _medicines_public(self, prescription_id: str) -> list[dict[str, Any]]:
        rows = await self.medicine_repo.list_by_prescription(prescription_id)
        out: list[dict[str, Any]] = []
        for m in rows:
            out.append(
                {
                    "medicine_id": m["_id"],
                    "name": m["name"],
                    "dosage_pattern": m["dosage_pattern"],
                    "frequency": m.get("frequency", 0),
                    "duration_days": m.get("duration_days", 30),
                    "instructions": m.get("instructions"),
                    "confidence": float(m.get("confidence", 0.0)),
                    "reminder_times_24h": list(m.get("reminder_times_24h") or []),
                }
            )
        return out
