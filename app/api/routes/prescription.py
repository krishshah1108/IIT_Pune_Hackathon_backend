"""Prescription routes."""

import logging
from uuid import uuid4

from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile, status

from app.api.dependencies import get_orchestrator, get_prescription_service, get_token_payload
from app.core.config import get_settings
from app.core.demo_prescriptions import demo_prescription_id_for_user
from app.core.exceptions import ConflictError, NotFoundError, ValidationError
from app.orchestrator.engine import OrchestratorEngine
from app.orchestrator.events import Event
from app.schemas.prescription import (
    PrescriptionConfirmRequest,
    PrescriptionConfirmResponse,
    PrescriptionUploadResponse,
    SavedMedicineOut,
)
from app.services.prescription_service import PrescriptionService

router = APIRouter(prefix="/prescriptions", tags=["prescriptions"])
logger = logging.getLogger(__name__)

_ALLOWED_IMAGE_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


def _upload_response_from_doc(doc: dict, event_id: str) -> PrescriptionUploadResponse:
    st = doc["status"]
    raw_ai = doc.get("ai_output") or {}
    analysis = raw_ai if st in ("awaiting_confirmation", "failed", "confirmed") and raw_ai else None
    return PrescriptionUploadResponse(
        success=True,
        prescription_id=doc["_id"],
        event_id=event_id,
        status=st,
        user_id=doc["user_id"],
        language=str(doc.get("language", "en")),
        image_url=doc.get("image_url"),
        created_at=doc["created_at"],
        updated_at=doc.get("updated_at"),
        analysis=analysis,
    )


def _failed_upload_detail(doc: dict) -> str:
    """Best-effort user-facing failure detail from AI output."""
    ai_output = doc.get("ai_output") or {}
    if isinstance(ai_output, dict):
        top_error = str(ai_output.get("error") or "").strip()
        if top_error:
            return f"Prescription processing failed: {top_error}"
        vision = ai_output.get("vision") or {}
        if isinstance(vision, dict):
            vision_error = str(vision.get("error") or "").strip()
            if vision_error:
                return f"Prescription processing failed: {vision_error}"
    return "Prescription processing failed. Please re-upload a clearer image."


@router.post("/upload", response_model=PrescriptionUploadResponse)
async def upload_prescription(
    claims: dict = Depends(get_token_payload),
    language: str = Form(default="en", min_length=2, max_length=8),
    image: UploadFile = File(..., description="Prescription image (JPEG, PNG, or WebP)"),
    service: PrescriptionService = Depends(get_prescription_service),
    orchestrator: OrchestratorEngine = Depends(get_orchestrator),
) -> PrescriptionUploadResponse:
    """Upload image, run vision + literacy + food in-process, return draft analysis (no medicines until confirm)."""
    user_id = str(claims["sub"])
    logger.info("prescription.upload.received user_id=%s filename=%s", user_id, image.filename or "unknown")
    content_type = (image.content_type or "").split(";")[0].strip().lower()
    if content_type not in _ALLOWED_IMAGE_TYPES:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Invalid image type. Allowed: image/jpeg, image/png, image/webp.",
        )

    raw = await image.read()
    if not raw:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Empty image file.")
    logger.info("prescription.upload.file_read user_id=%s bytes=%s content_type=%s", user_id, len(raw), content_type)

    settings = get_settings()
    demo_prx = demo_prescription_id_for_user(user_id) if settings.demo_mode else None

    if demo_prx:
        try:
            prescription = await service.apply_demo_prescription_upload(
                user_id=user_id,
                demo_prescription_id=demo_prx,
                file_bytes=raw,
                content_type=content_type,
                original_filename=image.filename,
                language=language,
            )
        except NotFoundError as exc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
        except ValueError as exc:
            raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc
        logger.info(
            "prescription.upload.demo_shortcut user_id=%s prescription_id=%s image_url=%s",
            user_id,
            prescription["_id"],
            prescription.get("image_url"),
        )
        doc = await service.get_owned_prescription(user_id, prescription["_id"])
        if not doc:
            raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Prescription missing after processing")
        return _upload_response_from_doc(doc, str(uuid4()))

    try:
        prescription = await service.create_upload_from_file(
            user_id=user_id,
            file_bytes=raw,
            content_type=content_type,
            original_filename=image.filename,
            language=language,
        )
        logger.info(
            "prescription.upload.cloudinary.done user_id=%s prescription_id=%s image_url=%s",
            user_id,
            prescription["_id"],
            prescription.get("image_url"),
        )
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValueError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    event = Event(
        event_type="prescription_uploaded",
        payload={
            "prescription_id": prescription["_id"],
            "user_id": prescription["user_id"],
            "language": language,
            "image_url": prescription["image_url"],
        },
    )
    await orchestrator.publish(event)
    logger.info("prescription.upload.pipeline.done user_id=%s prescription_id=%s event_id=%s", user_id, prescription["_id"], event.event_id)

    doc = await service.get_owned_prescription(user_id, prescription["_id"])
    if not doc:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail="Prescription missing after processing")
    if doc.get("status") == "failed":
        detail = _failed_upload_detail(doc)
        await service.discard_failed_upload(user_id=user_id, prescription_id=prescription["_id"])
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=detail)
    return _upload_response_from_doc(doc, event.event_id)


@router.post("/{prescription_id}/confirm", response_model=PrescriptionConfirmResponse)
async def confirm_prescription(
    prescription_id: str,
    payload: PrescriptionConfirmRequest,
    claims: dict = Depends(get_token_payload),
    service: PrescriptionService = Depends(get_prescription_service),
) -> PrescriptionConfirmResponse:
    """Persist medicines + dose schedules after user reviews the AI draft."""
    user_id = str(claims["sub"])
    meds = None if payload.medicines is None else [m.model_dump() for m in payload.medicines]
    try:
        result = await service.confirm_prescription(user_id, prescription_id, meds)
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(exc)) from exc

    return PrescriptionConfirmResponse(
        success=True,
        prescription_id=result["prescription_id"],
        status=result["status"],
        medicines=[SavedMedicineOut(**m) for m in result["medicines"]],
        idempotent=result.get("idempotent", False),
    )
