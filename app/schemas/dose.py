"""Dose tracking schemas."""

from datetime import datetime
from pydantic import BaseModel, Field


class DoseLogRequest(BaseModel):
    """Update dose status payload."""

    dose_log_id: str = Field(min_length=8)
    status: str = Field(pattern="^(taken|missed|skipped)$")
    taken_at: datetime | None = None


class DoseLogResponse(BaseModel):
    """Dose log response."""

    success: bool
    message: str


class MissedDoseSummary(BaseModel):
    """Missed dose analytics."""

    user_id: str
    missed_count: int
    last_missed_at: datetime | None = None


class DoseCalendarDay(BaseModel):
    """Calendar summary for one day."""

    date: str
    total: int
    taken: int
    missed: int
    skipped: int
    pending: int


class DoseCalendarResponse(BaseModel):
    """Month-level dose summary for dashboard calendar."""

    success: bool
    month: str
    tz: str
    days: list[DoseCalendarDay]


class DoseDayItem(BaseModel):
    """Single dose row for a selected date."""

    dose_log_id: str
    medicine_id: str
    medicine_name: str
    scheduled_for: datetime
    status: str
    taken_at: datetime | None = None


class DoseDayResponse(BaseModel):
    """All doses scheduled for one selected date."""

    success: bool
    date: str
    tz: str
    items: list[DoseDayItem]
