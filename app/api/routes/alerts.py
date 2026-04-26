"""Alert timeline routes."""

from fastapi import APIRouter, Depends, Query

from app.api.dependencies import get_alert_service, get_token_payload
from app.schemas.alert import AlertItem, AlertListResponse
from app.services.alert_service import AlertService

router = APIRouter(prefix="/alerts", tags=["alerts"])


@router.get("", response_model=AlertListResponse)
async def list_alerts(
    claims: dict = Depends(get_token_payload),
    limit: int = Query(default=50, ge=1, le=200),
    service: AlertService = Depends(get_alert_service),
) -> AlertListResponse:
    """List recent alerts for authenticated user."""
    user_id = str(claims["sub"])
    rows = await service.list_alerts(user_id=user_id, limit=limit)
    items = [
        AlertItem(
            alert_id=row["_id"],
            user_id=row["user_id"],
            severity=row.get("severity", "warning"),
            message=row.get("message", ""),
            status=row.get("status", "queued"),
            delivery_channel=row.get("delivery_channel", "email"),
            delivery_status=row.get("delivery_status", row.get("status", "queued")),
            failure_reason=row.get("failure_reason"),
            sent_at=row.get("sent_at"),
            created_at=row["created_at"],
            updated_at=row["updated_at"],
        )
        for row in rows
    ]
    return AlertListResponse(items=items)
