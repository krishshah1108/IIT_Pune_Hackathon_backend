"""Medicine listing routes."""

from fastapi import APIRouter, Depends

from app.api.dependencies import get_medicine_repo, get_token_payload
from app.repositories.medicine_repository import MedicineRepository
from app.schemas.medicine import MedicineListResponse

router = APIRouter(prefix="/medicines", tags=["medicines"])


@router.get("", response_model=MedicineListResponse)
async def list_medicines(
    claims: dict = Depends(get_token_payload),
    repo: MedicineRepository = Depends(get_medicine_repo),
) -> MedicineListResponse:
    """Return medicines saved for the authenticated user."""
    user_id = str(claims["sub"])
    rows = await repo.list_by_user(user_id=user_id)
    items = [
        {
            "medicine_id": row["_id"],
            "prescription_id": row["prescription_id"],
            "name": row.get("name") or "",
            "dosage_pattern": row.get("dosage_pattern") or "",
            "frequency": int(row.get("frequency", 0)),
            "duration_days": int(row.get("duration_days", 30)),
            "instructions": row.get("instructions"),
            "confidence": float(row.get("confidence", 0.0)),
            "reminder_times_24h": list(row.get("reminder_times_24h") or []),
        }
        for row in rows
    ]
    return MedicineListResponse(success=True, items=items)
