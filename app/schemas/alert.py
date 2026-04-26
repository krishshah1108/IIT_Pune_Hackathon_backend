"""Alert API schemas."""

from datetime import datetime

from pydantic import BaseModel, Field


class AlertItem(BaseModel):
    """One alert row for timeline."""

    alert_id: str
    user_id: str
    severity: str
    message: str
    status: str
    delivery_channel: str = "email"
    delivery_status: str
    failure_reason: str | None = None
    sent_at: datetime | None = None
    created_at: datetime
    updated_at: datetime


class AlertListResponse(BaseModel):
    """Alert timeline response."""

    success: bool = True
    items: list[AlertItem] = Field(default_factory=list)
