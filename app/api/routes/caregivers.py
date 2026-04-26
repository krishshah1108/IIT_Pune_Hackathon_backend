"""Caregiver CRUD — multiple caregivers per user (patient)."""

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.api.dependencies import get_caregiver_repo, get_token_payload
from app.repositories.caregiver_repository import CaregiverRepository
from app.schemas.caregiver import (
    CaregiverBaseResponse,
    CaregiverListResponse,
    CaregiverSingleResponse,
    CreateCaregiverRequest,
    DeleteCaregiverResponse,
    UpdateCaregiverRequest,
)

router = APIRouter(prefix="/caregivers", tags=["caregivers"])


@router.get("", response_model=CaregiverListResponse)
async def list_caregivers(
    include_inactive: bool = Query(False, description="Include caregivers with is_active=false (still excludes soft-deleted)"),
    claims: dict = Depends(get_token_payload),
    repo: CaregiverRepository = Depends(get_caregiver_repo),
) -> CaregiverListResponse:
    """List caregivers for the current user. Soft-deleted rows are never returned."""
    user_id = str(claims["sub"])
    docs = await repo.list_by_user(user_id, include_inactive=include_inactive)
    items = [CaregiverBaseResponse.from_doc(d) for d in docs]
    return CaregiverListResponse(items=items)


@router.post("", response_model=CaregiverSingleResponse, status_code=status.HTTP_201_CREATED)
async def create_caregiver(
    body: CreateCaregiverRequest,
    claims: dict = Depends(get_token_payload),
    repo: CaregiverRepository = Depends(get_caregiver_repo),
) -> CaregiverSingleResponse:
    """Add a caregiver. Email must be unique per user among non-deleted caregivers."""
    user_id = str(claims["sub"])
    if await repo.email_taken(user_id, str(body.email)):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A caregiver with this email already exists for your account",
        )
    doc = await repo.create(
        user_id,
        display_name=body.display_name,
        email=str(body.email),
        phone=body.phone,
        relationship_label=body.relationship_label,
        is_active=body.is_active,
        notify_on_missed_dose=body.notify_on_missed_dose,
    )
    return CaregiverSingleResponse(item=CaregiverBaseResponse.from_doc(doc))


@router.get("/{caregiver_id}", response_model=CaregiverSingleResponse)
async def get_caregiver(
    caregiver_id: str,
    claims: dict = Depends(get_token_payload),
    repo: CaregiverRepository = Depends(get_caregiver_repo),
) -> CaregiverSingleResponse:
    user_id = str(claims["sub"])
    doc = await repo.get_by_id(caregiver_id, user_id)
    if not doc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caregiver not found")
    return CaregiverSingleResponse(item=CaregiverBaseResponse.from_doc(doc))


@router.patch("/{caregiver_id}", response_model=CaregiverSingleResponse)
async def update_caregiver(
    caregiver_id: str,
    body: UpdateCaregiverRequest,
    claims: dict = Depends(get_token_payload),
    repo: CaregiverRepository = Depends(get_caregiver_repo),
) -> CaregiverSingleResponse:
    user_id = str(claims["sub"])
    patch = body.model_dump(exclude_unset=True)
    if "email" in patch and patch["email"] is not None:
        patch["email"] = str(patch["email"])
    if not patch:
        doc = await repo.get_by_id(caregiver_id, user_id)
        if not doc:
            raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caregiver not found")
        return CaregiverSingleResponse(item=CaregiverBaseResponse.from_doc(doc))
    if "email" in patch and await repo.email_taken(user_id, patch["email"], except_id=caregiver_id):
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="A caregiver with this email already exists for your account",
        )
    updated = await repo.update(caregiver_id, user_id, patch)
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caregiver not found")
    return CaregiverSingleResponse(item=CaregiverBaseResponse.from_doc(updated))


@router.delete("/{caregiver_id}", response_model=DeleteCaregiverResponse)
async def delete_caregiver(
    caregiver_id: str,
    claims: dict = Depends(get_token_payload),
    repo: CaregiverRepository = Depends(get_caregiver_repo),
) -> DeleteCaregiverResponse:
    """Soft-delete a caregiver (sets deleted_at, is_active=false). Idempotent: missing already-deleted returns 404."""
    user_id = str(claims["sub"])
    ok = await repo.soft_delete(caregiver_id, user_id)
    if not ok:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Caregiver not found")
    return DeleteCaregiverResponse(
        message="Caregiver removed",
        caregiver_id=caregiver_id,
    )
