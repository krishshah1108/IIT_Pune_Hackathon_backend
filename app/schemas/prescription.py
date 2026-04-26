"""Prescription API schemas."""

import re
from datetime import datetime
from typing import Any

from pydantic import BaseModel, Field, field_validator


_HHMM = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")


class PrescriptionUploadResponse(BaseModel):
    """Upload + synchronous AI draft: same HTTP request waits for vision / literacy / food."""

    success: bool
    prescription_id: str
    event_id: str
    status: str
    user_id: str
    language: str
    image_url: str | None = None
    created_at: datetime
    updated_at: datetime | None = None
    analysis: dict[str, Any] | None = None


class SavedMedicineOut(BaseModel):
    """Medicine row after user confirmation (DB-backed)."""

    medicine_id: str
    name: str
    dosage_pattern: str
    frequency: int
    duration_days: int
    instructions: str | None = None
    confidence: float
    reminder_times_24h: list[str] = Field(default_factory=list)


class ConfirmMedicineItem(BaseModel):
    """User-edited medicine line for confirm (same shape as vision draft)."""

    name: str = Field(min_length=1, max_length=400)
    dosage_pattern: str = Field(min_length=1, max_length=400)
    duration_days: int = Field(default=30, ge=1, le=3650)
    instructions: str | None = Field(default=None, max_length=2000)
    confidence: float = Field(default=0.75, ge=0.0, le=1.0)
    reminder_times_24h: list[str] | None = None

    @field_validator("reminder_times_24h")
    @classmethod
    def validate_times(cls, v: list[str] | None) -> list[str] | None:
        if v is None:
            return None
        out: list[str] = []
        for t in v:
            s = str(t).strip()
            if not _HHMM.match(s):
                raise ValueError(f"Invalid reminder time (use HH:MM 24h): {t!r}")
            out.append(s)
        return out


class PrescriptionConfirmRequest(BaseModel):
    """Send null/omit medicines to confirm the AI draft without edits."""

    medicines: list[ConfirmMedicineItem] | None = None


class PrescriptionConfirmResponse(BaseModel):
    """Medicines and dose schedules persisted after confirm."""

    success: bool
    prescription_id: str
    status: str
    medicines: list[SavedMedicineOut]
    idempotent: bool = False
