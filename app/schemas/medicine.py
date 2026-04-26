"""Medicine API schemas."""

from pydantic import BaseModel


class MedicineItem(BaseModel):
    """Single medicine row for app listing."""

    medicine_id: str
    prescription_id: str
    name: str
    dosage_pattern: str
    frequency: int
    duration_days: int
    instructions: str | None = None
    confidence: float
    reminder_times_24h: list[str]


class MedicineListResponse(BaseModel):
    """List medicines for authenticated user."""

    success: bool
    items: list[MedicineItem]
