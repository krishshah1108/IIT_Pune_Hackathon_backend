"""Orchestrator engine."""

import logging
from datetime import datetime, timezone
from typing import Any

from app.agents.checkin_agent import CheckinAgent
from app.agents.food_agent import FoodAgent
from app.agents.literacy_agent import LiteracyAgent
from app.agents.triage_agent import TriageAgent
from app.agents.vision_agent import VisionAgent
from app.orchestrator.dispatcher import EventDispatcher
from app.orchestrator.events import Event
from app.repositories.event_repository import EventRepository
from app.repositories.prescription_repository import PrescriptionRepository
from app.services.alert_service import AlertService
from app.services.prescription_service import PrescriptionService

logger = logging.getLogger(__name__)


class OrchestratorEngine:
    """Coordinates all event-driven agent workflows."""

    def __init__(
        self,
        event_repo: EventRepository,
        prescription_repo: PrescriptionRepository,
        prescription_service: PrescriptionService,
        alert_service: AlertService,
        vision_agent: VisionAgent,
        literacy_agent: LiteracyAgent,
        food_agent: FoodAgent,
        checkin_agent: CheckinAgent,
        triage_agent: TriageAgent,
    ):
        self.event_repo = event_repo
        self.prescription_repo = prescription_repo
        self.prescription_service = prescription_service
        self.alert_service = alert_service
        self.vision_agent = vision_agent
        self.literacy_agent = literacy_agent
        self.food_agent = food_agent
        self.checkin_agent = checkin_agent
        self.triage_agent = triage_agent
        self.dispatcher = EventDispatcher()
        self._register_handlers()

    def _register_handlers(self) -> None:
        self.dispatcher.register("prescription_uploaded", self.handle_prescription_uploaded)
        self.dispatcher.register("dose_missed", self.handle_dose_missed)
        self.dispatcher.register("alert_required", self.handle_alert_required)

    async def publish(self, event: Event) -> None:
        """Process event with idempotency protection."""
        logger.info("event.publish.received event_id=%s event_type=%s", event.event_id, event.event_type)
        is_new = await self.event_repo.register_event(event.event_id, event.event_type, event.payload)
        if not is_new:
            logger.info("event.duplicate event_id=%s event_type=%s", event.event_id, event.event_type)
            return
        logger.info("event.publish.dispatching event_id=%s event_type=%s", event.event_id, event.event_type)
        await self.dispatcher.dispatch(event)
        logger.info("event.publish.completed event_id=%s event_type=%s", event.event_id, event.event_type)

    async def handle_prescription_uploaded(self, event: Event) -> None:
        """Run vision + enrichment agents; persist draft for user confirmation (no medicines/doses until confirm)."""
        prescription_id = event.payload["prescription_id"]
        image_url = event.payload.get("image_url")
        image_base64 = event.payload.get("image_base64")
        logger.info(
            "prescription.pipeline.started event_id=%s prescription_id=%s",
            event.event_id,
            prescription_id,
        )

        await self.prescription_repo.update_status(prescription_id, "processing")

        vision_payload: dict[str, Any] = {"language": event.payload.get("language", "en")}
        if image_url:
            vision_payload["image_url"] = image_url
            logger.info(
                "prescription.pipeline.image.ready event_id=%s prescription_id=%s source=url",
                event.event_id,
                prescription_id,
            )
        elif image_base64:
            vision_payload["image_base64"] = image_base64
            logger.info(
                "prescription.pipeline.image.ready event_id=%s prescription_id=%s source=base64",
                event.event_id,
                prescription_id,
            )
        else:
            await self.prescription_repo.update_status(
                prescription_id,
                "failed",
                {"vision": {"status": "failed", "error": "missing_image_reference", "medicines": [], "confidence": 0.0}},
            )
            return
        try:
            vision = await self.vision_agent.run(vision_payload)
            logger.info(
                "prescription.pipeline.vision.done event_id=%s prescription_id=%s status=%s medicines=%s",
                event.event_id,
                prescription_id,
                vision.get("status"),
                len(vision.get("medicines") or []),
            )
        except RuntimeError as exc:
            err_text = str(exc).strip().lower()
            if "non-json response" in err_text:
                logger.warning(
                    "prescription.pipeline.vision.failed event_id=%s prescription_id=%s error=gemini_non_json_response",
                    event.event_id,
                    prescription_id,
                )
                await self.prescription_repo.update_status(
                    prescription_id,
                    "failed",
                    {
                        "vision": {
                            "status": "failed",
                            "error": "gemini_non_json_response",
                            "medicines": [],
                            "confidence": 0.0,
                        }
                    },
                )
                return
            logger.exception("agent.failed")
            await self.prescription_repo.update_status(
                prescription_id,
                "failed",
                {
                    "vision": {
                        "status": "failed",
                        "error": "vision_unavailable",
                        "medicines": [],
                        "confidence": 0.0,
                    }
                },
            )
            return
        except Exception:
            logger.exception("agent.failed")
            await self.prescription_repo.update_status(
                prescription_id,
                "failed",
                {
                    "vision": {
                        "status": "failed",
                        "error": "vision_unavailable",
                        "medicines": [],
                        "confidence": 0.0,
                    }
                },
            )
            return

        if vision.get("status") != "ok":
            logger.warning(
                "prescription.pipeline.vision.failed event_id=%s prescription_id=%s status=%s",
                event.event_id,
                prescription_id,
                vision.get("status"),
            )
            await self.prescription_repo.update_status(prescription_id, "failed", {"vision": vision})
            return

        medicines = vision.get("medicines") or []
        if not medicines:
            logger.warning(
                "prescription.pipeline.vision.no_medicines event_id=%s prescription_id=%s",
                event.event_id,
                prescription_id,
            )
            await self.prescription_repo.update_status(
                prescription_id,
                "failed",
                {"vision": vision, "error": "no_medicines_from_vision"},
            )
            return

        lang = event.payload.get("language", "en")
        enrich_payload: dict[str, Any] = {"medicines": medicines, "language": lang}

        # Sequential: avoids Gemini free-tier parallel burst (HTTP 429).
        literacy = await self.literacy_agent.run(enrich_payload)
        logger.info(
            "prescription.pipeline.literacy.done event_id=%s prescription_id=%s status=%s",
            event.event_id,
            prescription_id,
            literacy.get("status"),
        )
        food = await self.food_agent.run(enrich_payload)
        logger.info(
            "prescription.pipeline.food.done event_id=%s prescription_id=%s status=%s",
            event.event_id,
            prescription_id,
            food.get("status"),
        )

        draft_output: dict[str, Any] = {
            "vision": vision,
            "literacy": literacy,
            "food": food,
            "draft_ready_at": datetime.now(timezone.utc).isoformat(),
        }
        await self.prescription_repo.update_status(prescription_id, "awaiting_confirmation", draft_output)
        logger.info(
            "prescription.pipeline.completed event_id=%s prescription_id=%s status=awaiting_confirmation",
            event.event_id,
            prescription_id,
        )

    async def handle_dose_missed(self, event: Event) -> None:
        """Run check-in and triage pipeline for missed dose."""
        logger.info(
            "event.handle_dose_missed.started event_id=%s user_id=%s dose_log_id=%s status=%s consecutive_misses=%s",
            event.event_id,
            event.payload.get("user_id"),
            event.payload.get("dose_log_id"),
            event.payload.get("status"),
            event.payload.get("consecutive_misses"),
        )
        checkin = await self.checkin_agent.run(event.payload)
        logger.info("event.handle_dose_missed.checkin_result event_id=%s risk_level=%s", event.event_id, checkin.get("risk_level"))
        triage = await self.triage_agent.run(
            {
                "risk_level": checkin.get("risk_level", "low"),
                "status": event.payload.get("status"),
                "consecutive_misses": int(event.payload.get("consecutive_misses", 0)),
            }
        )
        logger.info(
            "event.handle_dose_missed.triage_result event_id=%s status=%s escalate=%s severity=%s",
            event.event_id,
            event.payload.get("status"),
            triage.get("escalate"),
            triage.get("severity"),
        )

        if triage.get("escalate"):
            logger.info("event.handle_dose_missed.alert_required event_id=%s", event.event_id)
            alert_event = Event(
                event_type="alert_required",
                payload={
                    "user_id": event.payload["user_id"],
                    "severity": triage.get("severity", "critical"),
                    "message": "Critical non-adherence detected. Please check on patient.",
                },
            )
            await self.publish(alert_event)
        else:
            logger.info("event.handle_dose_missed.no_alert event_id=%s", event.event_id)

    async def handle_alert_required(self, event: Event) -> None:
        """Create and dispatch caregiver alert."""
        logger.info(
            "event.handle_alert_required.started event_id=%s user_id=%s severity=%s",
            event.event_id,
            event.payload.get("user_id"),
            event.payload.get("severity"),
        )
        await self.alert_service.create_and_send(
            user_id=event.payload["user_id"],
            severity=event.payload["severity"],
            message=event.payload["message"],
        )
        logger.info("event.handle_alert_required.completed event_id=%s", event.event_id)
