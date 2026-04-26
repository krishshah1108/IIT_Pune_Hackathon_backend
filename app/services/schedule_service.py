"""Schedule generation service."""

from datetime import datetime, timedelta, timezone

from app.utils.normalization import parse_frequency
from app.utils.reminder_times import parse_hhmm_list


class ScheduleService:
    """Generate dose schedules from dosage patterns."""

    def generate_schedule(
        self,
        dosage_pattern: str,
        duration_days: int,
        start_at: datetime | None = None,
        reminder_times_24h: list[str] | None = None,
    ) -> list[datetime]:
        """Build schedule timestamps for dose logs.

        If user-confirmed reminder times are provided, those times are used for each day.
        Otherwise, schedule falls back to frequency-based spacing from dosage_pattern.
        """
        if duration_days <= 0:
            return []

        base_start = start_at or datetime.now(timezone.utc)
        day0 = base_start.replace(hour=0, minute=0, second=0, microsecond=0)
        parsed_times = parse_hhmm_list(reminder_times_24h) if reminder_times_24h else []

        schedule: list[datetime] = []
        if parsed_times:
            for day in range(duration_days):
                day_base = day0 + timedelta(days=day)
                for hhmm in parsed_times:
                    hour = int(hhmm[:2])
                    minute = int(hhmm[3:5])
                    schedule.append(day_base.replace(hour=hour, minute=minute))
            return sorted(schedule)

        start = day0.replace(hour=8, minute=0)
        frequency = max(parse_frequency(dosage_pattern), 1)
        per_day_hours = max(24 // frequency, 1)
        for day in range(duration_days):
            day_base = start + timedelta(days=day)
            for slot in range(frequency):
                schedule.append(day_base + timedelta(hours=slot * per_day_hours))
        return schedule
