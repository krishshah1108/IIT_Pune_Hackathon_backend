"""Dose tracking routes."""

import logging
from datetime import datetime
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_adherence_service, get_orchestrator, get_token_payload
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.events import Event
from app.schemas.dose import DoseCalendarResponse, DoseDayResponse, DoseLogRequest, DoseLogResponse
from app.services.adherence_service import AdherenceService

router = APIRouter(prefix="/doses", tags=["doses"])
logger = logging.getLogger(__name__)


def _validate_month_format(month: str) -> None:
    try:
        datetime.strptime(month, "%Y-%m")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="month must be in YYYY-MM format") from exc


def _validate_date_format(date_str: str) -> None:
    try:
        datetime.strptime(date_str, "%Y-%m-%d")
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="date must be in YYYY-MM-DD format") from exc


def _validate_timezone(tz_name: str) -> None:
    try:
        ZoneInfo(tz_name)
    except ZoneInfoNotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail="Invalid timezone") from exc


@router.post("/log", response_model=DoseLogResponse)
async def update_dose_log(
    payload: DoseLogRequest,
    claims: dict = Depends(get_token_payload),
    service: AdherenceService = Depends(get_adherence_service),
    orchestrator: OrchestratorEngine = Depends(get_orchestrator),
) -> DoseLogResponse:
    """Update dose adherence status (JWT required; log must belong to caller)."""
    user_id = str(claims["sub"])
    logger.info(
        "dose.log.update.received user_id=%s dose_log_id=%s status=%s",
        user_id,
        payload.dose_log_id,
        payload.status,
    )
    context = await service.update_dose_for_user_with_context(user_id, payload.dose_log_id, payload.status, payload.taken_at)
    if not context:
        logger.warning("dose.log.update.not_found user_id=%s dose_log_id=%s", user_id, payload.dose_log_id)
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Dose log not found")
    logger.info(
        "dose.log.update.success user_id=%s dose_log_id=%s status=%s consecutive_misses=%s",
        context["user_id"],
        context["dose_log_id"],
        context["status"],
        context.get("consecutive_misses"),
    )

    # Policy: user-marked skipped/missed should also be triaged, not only worker-marked missed.
    if payload.status in {"skipped", "missed"}:
        logger.info(
            "dose.log.update.triage_triggered user_id=%s dose_log_id=%s status=%s consecutive_misses=%s",
            context["user_id"],
            context["dose_log_id"],
            payload.status,
            context.get("consecutive_misses"),
        )
        event = Event(
            event_type="dose_missed",
            payload={
                "user_id": context["user_id"],
                "dose_log_id": context["dose_log_id"],
                "status": payload.status,
                "consecutive_misses": int(context.get("consecutive_misses", 1)),
            },
        )
        await orchestrator.publish(event)
    else:
        logger.info("dose.log.update.triage_not_required user_id=%s dose_log_id=%s status=%s", user_id, payload.dose_log_id, payload.status)
    return DoseLogResponse(success=True, message="Dose log updated")


@router.get("/calendar", response_model=DoseCalendarResponse)
async def get_month_calendar(
    month: str,
    tz: str = "UTC",
    claims: dict = Depends(get_token_payload),
    service: AdherenceService = Depends(get_adherence_service),
) -> DoseCalendarResponse:
    """Return dashboard month calendar summary for current user."""
    _validate_month_format(month)
    _validate_timezone(tz)
    user_id = str(claims["sub"])
    logger.info("dose.calendar.requested user_id=%s month=%s tz=%s", user_id, month, tz)
    payload = await service.get_calendar_summary(user_id=user_id, month=month, tz_name=tz)
    return DoseCalendarResponse(**payload)


@router.get("/day", response_model=DoseDayResponse)
async def get_day_doses(
    date: str,
    tz: str = "UTC",
    claims: dict = Depends(get_token_payload),
    service: AdherenceService = Depends(get_adherence_service),
) -> DoseDayResponse:
    """Return all dose entries for selected day for current user."""
    _validate_date_format(date)
    _validate_timezone(tz)
    user_id = str(claims["sub"])
    logger.info("dose.day.requested user_id=%s date=%s tz=%s", user_id, date, tz)
    payload = await service.get_day_details(user_id=user_id, date_str=date, tz_name=tz)
    return DoseDayResponse(**payload)
