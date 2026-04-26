"""Dose adherence and missed-dose handling service."""

import calendar
from datetime import datetime, timedelta, timezone
import logging
from zoneinfo import ZoneInfo

from app.core.config import get_settings
from app.repositories.dose_log_repository import DoseLogRepository

logger = logging.getLogger(__name__)


class AdherenceService:
    """Handle dose updates and missed dose scans."""

    def __init__(self, dose_repo: DoseLogRepository):
        self.dose_repo = dose_repo
        self.settings = get_settings()

    @staticmethod
    def _month_bounds_utc(month: str, tz_name: str) -> tuple[datetime, datetime, ZoneInfo]:
        """Convert YYYY-MM month boundaries from local tz into UTC [start, end)."""
        month_start_local = datetime.strptime(month, "%Y-%m").replace(day=1, hour=0, minute=0, second=0, microsecond=0)
        tz = ZoneInfo(tz_name)
        start_utc = month_start_local.replace(tzinfo=tz).astimezone(timezone.utc)
        if month_start_local.month == 12:
            next_month_local = month_start_local.replace(year=month_start_local.year + 1, month=1)
        else:
            next_month_local = month_start_local.replace(month=month_start_local.month + 1)
        end_utc = next_month_local.replace(tzinfo=tz).astimezone(timezone.utc)
        return start_utc, end_utc, tz

    @staticmethod
    def _day_bounds_utc(date_str: str, tz_name: str) -> tuple[datetime, datetime, ZoneInfo]:
        """Convert YYYY-MM-DD day boundaries from local tz into UTC [start, end)."""
        day_local = datetime.strptime(date_str, "%Y-%m-%d").replace(hour=0, minute=0, second=0, microsecond=0)
        tz = ZoneInfo(tz_name)
        start_utc = day_local.replace(tzinfo=tz).astimezone(timezone.utc)
        end_utc = (day_local + timedelta(days=1)).replace(tzinfo=tz).astimezone(timezone.utc)
        return start_utc, end_utc, tz

    async def update_dose(self, dose_log_id: str, status: str, taken_at: datetime | None) -> bool:
        """Update dose status."""
        logger.info("adherence.update_dose.started dose_log_id=%s status=%s", dose_log_id, status)
        return await self.dose_repo.update_status(dose_log_id, status, taken_at)

    async def update_dose_for_user(
        self,
        user_id: str,
        dose_log_id: str,
        status: str,
        taken_at: datetime | None,
    ) -> bool:
        """Update dose status only for logs owned by user_id."""
        logger.info(
            "adherence.update_dose_for_user.started user_id=%s dose_log_id=%s status=%s",
            user_id,
            dose_log_id,
            status,
        )
        return await self.dose_repo.update_status_for_user(dose_log_id, user_id, status, taken_at)

    async def update_dose_for_user_with_context(
        self,
        user_id: str,
        dose_log_id: str,
        status: str,
        taken_at: datetime | None,
    ) -> dict | None:
        """Update dose and return context for downstream event decisions."""
        updated = await self.update_dose_for_user(user_id, dose_log_id, status, taken_at)
        if not updated:
            logger.warning(
                "adherence.update_with_context.not_updated user_id=%s dose_log_id=%s status=%s",
                user_id,
                dose_log_id,
                status,
            )
            return None
        row = await self.dose_repo.get_by_id_for_user(dose_log_id, user_id)
        if not row:
            logger.warning("adherence.update_with_context.row_missing user_id=%s dose_log_id=%s", user_id, dose_log_id)
            return None
        consecutive = await self.dose_repo.count_consecutive_nonadherence(
            user_id=user_id,
            medicine_id=row["medicine_id"],
            upto_scheduled_for=row["scheduled_for"],
        )
        logger.info(
            "adherence.update_with_context.success user_id=%s dose_log_id=%s status=%s consecutive_misses=%s",
            row["user_id"],
            row["_id"],
            row["status"],
            consecutive,
        )
        return {
            "dose_log_id": row["_id"],
            "user_id": row["user_id"],
            "medicine_id": row["medicine_id"],
            "scheduled_for": row["scheduled_for"],
            "status": row["status"],
            "consecutive_misses": consecutive,
        }

    async def detect_missed_doses(self) -> list[dict]:
        """Mark overdue doses as missed and return them."""
        threshold = datetime.now(timezone.utc) - timedelta(minutes=self.settings.missed_dose_grace_minutes)
        logger.info(
            "adherence.detect_missed.started threshold=%s grace_minutes=%s",
            threshold.isoformat(),
            self.settings.missed_dose_grace_minutes,
        )
        due = await self.dose_repo.get_due_missed(threshold)
        logger.info("adherence.detect_missed.due_count count=%s", len(due))
        out: list[dict] = []
        for row in due:
            logger.info("adherence.detect_missed.marking dose_log_id=%s user_id=%s", row["_id"], row["user_id"])
            await self.dose_repo.mark_missed(row["_id"])
            refreshed = await self.dose_repo.get_by_id_for_user(row["_id"], row["user_id"])
            if not refreshed:
                logger.warning("adherence.detect_missed.refreshed_missing dose_log_id=%s user_id=%s", row["_id"], row["user_id"])
                continue
            consecutive = await self.dose_repo.count_consecutive_nonadherence(
                user_id=refreshed["user_id"],
                medicine_id=refreshed["medicine_id"],
                upto_scheduled_for=refreshed["scheduled_for"],
            )
            refreshed["consecutive_misses"] = consecutive
            logger.info(
                "adherence.detect_missed.marked dose_log_id=%s user_id=%s consecutive_misses=%s",
                refreshed["_id"],
                refreshed["user_id"],
                consecutive,
            )
            out.append(refreshed)
        logger.info("adherence.detect_missed.completed marked_count=%s", len(out))
        return out

    async def get_calendar_summary(self, user_id: str, month: str, tz_name: str) -> dict:
        """Return one summary row per day for a month."""
        start_utc, end_utc, tz = self._month_bounds_utc(month, tz_name)
        rows = await self.dose_repo.list_for_user_between(user_id, start_utc, end_utc)
        month_start_local = datetime.strptime(month, "%Y-%m")
        day_count = calendar.monthrange(month_start_local.year, month_start_local.month)[1]
        summary: dict[str, dict[str, int | str]] = {}
        for day in range(1, day_count + 1):
            date_key = month_start_local.replace(day=day).date().isoformat()
            summary[date_key] = {
                "date": date_key,
                "total": 0,
                "taken": 0,
                "missed": 0,
                "skipped": 0,
                "pending": 0,
            }

        for row in rows:
            local_date = row["scheduled_for"].astimezone(tz).date().isoformat()
            bucket = summary.get(local_date)
            if not bucket:
                continue
            bucket["total"] = int(bucket["total"]) + 1
            status_value = str(row.get("status", "pending")).strip().lower()
            if status_value not in {"taken", "missed", "skipped", "pending"}:
                status_value = "pending"
            bucket[status_value] = int(bucket[status_value]) + 1

        days = [summary[date_key] for date_key in sorted(summary.keys())]
        logger.info("adherence.calendar_summary.completed user_id=%s month=%s days=%s", user_id, month, len(days))
        return {"success": True, "month": month, "tz": tz_name, "days": days}

    async def get_day_details(self, user_id: str, date_str: str, tz_name: str) -> dict:
        """Return detailed dose rows for one selected date."""
        start_utc, end_utc, _tz = self._day_bounds_utc(date_str, tz_name)
        rows = await self.dose_repo.list_detailed_for_user_between(user_id, start_utc, end_utc)
        items = [
            {
                "dose_log_id": row["_id"],
                "medicine_id": row["medicine_id"],
                "medicine_name": row.get("medicine_name") or "Unknown medicine",
                "scheduled_for": row["scheduled_for"],
                "status": row.get("status", "pending"),
                "taken_at": row.get("taken_at"),
            }
            for row in rows
        ]
        logger.info("adherence.day_details.completed user_id=%s date=%s items=%s", user_id, date_str, len(items))
        return {"success": True, "date": date_str, "tz": tz_name, "items": items}
