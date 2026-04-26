"""Background worker for missed dose detection."""

import asyncio
import logging

from app.core.config import get_settings
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.events import Event
from app.services.adherence_service import AdherenceService

logger = logging.getLogger(__name__)


async def run_missed_dose_worker(service: AdherenceService, orchestrator: OrchestratorEngine, stop_event: asyncio.Event) -> None:
    """Periodic worker to detect missed doses and emit events."""
    settings = get_settings()
    logger.info("worker.missed_dose.started interval_seconds=%s", settings.schedule_scan_interval_seconds)
    while not stop_event.is_set():
        try:
            logger.info("worker.missed_dose.scan.started")
            missed_rows = await service.detect_missed_doses()
            logger.info("worker.missed_dose.scan.completed missed_count=%s", len(missed_rows))
            for row in missed_rows:
                logger.info(
                    "worker.missed_dose.event_publishing user_id=%s dose_log_id=%s consecutive_misses=%s",
                    row["user_id"],
                    row["_id"],
                    row.get("consecutive_misses", 1),
                )
                event = Event(
                    event_type="dose_missed",
                    payload={
                        "user_id": row["user_id"],
                        "dose_log_id": row["_id"],
                        "status": row.get("status", "missed"),
                        "consecutive_misses": int(row.get("consecutive_misses", 1)),
                    },
                )
                await orchestrator.publish(event)
                logger.info("worker.missed_dose.event_published event_type=dose_missed dose_log_id=%s", row["_id"])
        except Exception:
            logger.exception("worker.missed_dose.failed")
        await asyncio.sleep(settings.schedule_scan_interval_seconds)
    logger.info("worker.missed_dose.stopped")
