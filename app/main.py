"""Application entrypoint."""

import asyncio
import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI, Request, status
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse
from starlette.exceptions import HTTPException as StarletteHTTPException

from app.agents.checkin_agent import CheckinAgent
from app.agents.food_agent import FoodAgent
from app.agents.gemini_client import GeminiTextClient
from app.agents.gemini_vision_client import GeminiVisionClient
from app.agents.literacy_agent import LiteracyAgent
from app.agents.triage_agent import TriageAgent
from app.agents.v0_client import V0Client
from app.agents.vision_agent import VisionAgent
from app.api.routes.auth import router as auth_router
from app.api.routes.alerts import router as alerts_router
from app.api.routes.caregivers import router as caregivers_router
from app.api.routes.users import router as users_router
from app.api.routes.dose import router as dose_router
from app.api.routes.health import router as health_router
from app.api.routes.medicines import router as medicines_router
from app.api.routes.prescription import router as prescription_router
from app.core.config import get_settings
from app.core.database import close_mongo_connection, connect_to_mongo, get_database
from app.core.logging import configure_logging
from app.orchestrator.engine import OrchestratorEngine
from app.repositories.alert_repository import AlertRepository
from app.repositories.caregiver_repository import CaregiverRepository
from app.repositories.dose_log_repository import DoseLogRepository
from app.repositories.event_repository import EventRepository
from app.repositories.medicine_repository import MedicineRepository
from app.repositories.prescription_repository import PrescriptionRepository
from app.repositories.user_repository import UserRepository
from app.services.adherence_service import AdherenceService
from app.services.alert_service import AlertService
from app.services.cloudinary_service import CloudinaryService
from app.services.prescription_service import PrescriptionService
from app.services.schedule_service import ScheduleService
from app.workers.missed_dose_worker import run_missed_dose_worker
from app.utils.email import EmailClient

settings = get_settings()
configure_logging(settings.app_log_level)
logger = logging.getLogger(__name__)


@asynccontextmanager
async def lifespan(_: FastAPI):
    """Initialize infrastructure and worker lifecycle."""
    await connect_to_mongo()

    db = get_database()
    vision = GeminiVisionClient()
    literacy = GeminiTextClient(model_name=settings.gemini_literacy_model)
    food = GeminiTextClient(model_name=settings.gemini_food_model)
    orchestrator = OrchestratorEngine(
        event_repo=EventRepository(db),
        prescription_repo=PrescriptionRepository(db),
        prescription_service=PrescriptionService(
            PrescriptionRepository(db),
            MedicineRepository(db),
            UserRepository(db),
            CloudinaryService(),
            DoseLogRepository(db),
            ScheduleService(),
        ),
        alert_service=AlertService(
            AlertRepository(db),
            CaregiverRepository(db),
            EmailClient(),
        ),
        vision_agent=VisionAgent(vision, V0Client()),
        literacy_agent=LiteracyAgent(literacy),
        food_agent=FoodAgent(food),
        checkin_agent=CheckinAgent(),
        triage_agent=TriageAgent(),
    )
    adherence_service = AdherenceService(DoseLogRepository(db))

    stop_event = asyncio.Event()
    worker = asyncio.create_task(run_missed_dose_worker(adherence_service, orchestrator, stop_event))
    try:
        yield
    finally:
        stop_event.set()
        worker.cancel()
        await close_mongo_connection()


app = FastAPI(title=settings.app_name, lifespan=lifespan)


@app.middleware("http")
async def log_error_responses(request: Request, call_next):
    """Log non-success HTTP status codes (4xx/5xx) to aid debugging; includes 405 wrong-method cases."""
    response = await call_next(request)
    if response.status_code >= 400:
        logger.warning(
            "http.error_response method=%s path=%s status_code=%s",
            request.method,
            request.url.path,
            response.status_code,
        )
    return response


@app.exception_handler(StarletteHTTPException)
async def http_exception_handler(_request: Request, exc: StarletteHTTPException) -> JSONResponse:
    """Log HTTPException details (4xx/5xx raised in routes)."""
    if exc.status_code >= 500:
        logger.error("app.http_exception status=%s detail=%s", exc.status_code, exc.detail)
    else:
        logger.warning("app.http_exception status=%s detail=%s", exc.status_code, exc.detail)
    return JSONResponse(status_code=exc.status_code, content={"detail": exc.detail})


@app.exception_handler(RequestValidationError)
async def validation_exception_handler(_request: Request, exc: RequestValidationError) -> JSONResponse:
    """Log body/query validation failures (422)."""
    errors = exc.errors() if hasattr(exc, "errors") else str(exc)
    logger.warning("app.request_validation_error errors=%s", errors)
    return JSONResponse(
        status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
        content={"detail": exc.errors(), "body": exc.body},
    )


@app.exception_handler(Exception)
async def unhandled_exception_handler(_request: Request, exc: Exception) -> JSONResponse:
    """Log and hide unexpected server errors."""
    logger.exception("app.unhandled_exception: %s", exc)
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content={"detail": "Internal server error"},
    )


app.include_router(health_router)
app.include_router(auth_router)
app.include_router(users_router)
app.include_router(caregivers_router)
app.include_router(alerts_router)
app.include_router(prescription_router)
app.include_router(dose_router)
app.include_router(medicines_router)
