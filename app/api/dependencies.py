"""Dependency graph."""

from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
from jwt.exceptions import ExpiredSignatureError, InvalidTokenError
from motor.motor_asyncio import AsyncIOMotorDatabase

from app.core.jwt_tokens import decode_access_token

from app.agents.checkin_agent import CheckinAgent
from app.agents.food_agent import FoodAgent
from app.agents.gemini_client import GeminiTextClient
from app.agents.gemini_vision_client import GeminiVisionClient
from app.agents.literacy_agent import LiteracyAgent
from app.agents.triage_agent import TriageAgent
from app.agents.vision_agent import VisionAgent
from app.core.config import get_settings
from app.core.database import get_database
from app.orchestrator.engine import OrchestratorEngine
from app.repositories.alert_repository import AlertRepository
from app.repositories.caregiver_repository import CaregiverRepository
from app.repositories.dose_log_repository import DoseLogRepository
from app.repositories.event_repository import EventRepository
from app.repositories.medicine_repository import MedicineRepository
from app.repositories.otp_repository import OTPRepository
from app.repositories.prescription_repository import PrescriptionRepository
from app.repositories.user_repository import UserRepository
from app.services.adherence_service import AdherenceService
from app.services.alert_service import AlertService
from app.services.cloudinary_service import CloudinaryService
from app.services.otp_service import OTPService
from app.services.prescription_service import PrescriptionService
from app.services.schedule_service import ScheduleService
from app.utils.email import EmailClient

_http_bearer = HTTPBearer(auto_error=False)


def get_bearer_token(
    credentials: HTTPAuthorizationCredentials | None = Depends(_http_bearer),
) -> str:
    if credentials is None or credentials.scheme.lower() != "bearer":
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Not authenticated")
    return credentials.credentials


def get_token_payload(token: str = Depends(get_bearer_token)) -> dict:
    """Validate `Authorization: Bearer <JWT>` and return claims (`sub`, `email`, …)."""
    try:
        return decode_access_token(token)
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Token expired") from None
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token") from None


def get_user_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> UserRepository:
    return UserRepository(db)


def get_caregiver_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> CaregiverRepository:
    return CaregiverRepository(db)


def get_otp_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> OTPRepository:
    return OTPRepository(db)


def get_prescription_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> PrescriptionRepository:
    return PrescriptionRepository(db)


def get_medicine_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> MedicineRepository:
    return MedicineRepository(db)


def get_dose_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> DoseLogRepository:
    return DoseLogRepository(db)


def get_alert_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> AlertRepository:
    return AlertRepository(db)


def get_alert_service(
    alert_repo: AlertRepository = Depends(get_alert_repo),
    caregiver_repo: CaregiverRepository = Depends(get_caregiver_repo),
) -> AlertService:
    return AlertService(alert_repo=alert_repo, caregiver_repo=caregiver_repo, email_client=EmailClient())


def get_event_repo(db: AsyncIOMotorDatabase = Depends(get_database)) -> EventRepository:
    return EventRepository(db)


def get_otp_service(otp_repo: OTPRepository = Depends(get_otp_repo), user_repo: UserRepository = Depends(get_user_repo)) -> OTPService:
    return OTPService(otp_repo=otp_repo, user_repo=user_repo, email_client=EmailClient())


def get_cloudinary_service() -> CloudinaryService:
    return CloudinaryService()


def get_prescription_service(
    prescription_repo: PrescriptionRepository = Depends(get_prescription_repo),
    medicine_repo: MedicineRepository = Depends(get_medicine_repo),
    user_repo: UserRepository = Depends(get_user_repo),
    cloudinary: CloudinaryService = Depends(get_cloudinary_service),
    dose_repo: DoseLogRepository = Depends(get_dose_repo),
) -> PrescriptionService:
    return PrescriptionService(
        prescription_repo,
        medicine_repo,
        user_repo,
        cloudinary,
        dose_repo,
        ScheduleService(),
    )


def get_adherence_service(dose_repo: DoseLogRepository = Depends(get_dose_repo)) -> AdherenceService:
    return AdherenceService(dose_repo)


def get_orchestrator(
    event_repo: EventRepository = Depends(get_event_repo),
    prescription_repo: PrescriptionRepository = Depends(get_prescription_repo),
    prescription_service: PrescriptionService = Depends(get_prescription_service),
    alert_service: AlertService = Depends(get_alert_service),
) -> OrchestratorEngine:
    settings = get_settings()
    vision = GeminiVisionClient()
    literacy = GeminiTextClient(model_name=settings.gemini_literacy_model)
    food = GeminiTextClient(model_name=settings.gemini_food_model)
    return OrchestratorEngine(
        event_repo=event_repo,
        prescription_repo=prescription_repo,
        prescription_service=prescription_service,
        alert_service=alert_service,
        vision_agent=VisionAgent(vision),
        literacy_agent=LiteracyAgent(literacy),
        food_agent=FoodAgent(food),
        checkin_agent=CheckinAgent(),
        triage_agent=TriageAgent(),
    )
