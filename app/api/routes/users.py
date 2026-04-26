"""User profile routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_token_payload, get_user_repo
from app.repositories.user_repository import UserRepository
from app.schemas.user import ProfileResponse, UpdateProfileRequest, UpdateProfileResponse

router = APIRouter(prefix="/users", tags=["users"])


@router.get("/profile", response_model=ProfileResponse)
async def get_profile(
    claims: dict = Depends(get_token_payload),
    user_repo: UserRepository = Depends(get_user_repo),
) -> ProfileResponse:
    """Return current user profile (JWT required)."""
    user_id = str(claims["sub"])
    user = await user_repo.get_by_id(user_id)
    if not user:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    return ProfileResponse(
        user_id=user["_id"],
        email=user["email"],
        first_name=user.get("first_name") or "",
        last_name=user.get("last_name") or "",
        last_login_at=user.get("last_login_at"),
    )


@router.patch("/profile", response_model=UpdateProfileResponse)
async def update_profile(
    payload: UpdateProfileRequest,
    claims: dict = Depends(get_token_payload),
    user_repo: UserRepository = Depends(get_user_repo),
) -> UpdateProfileResponse:
    """Update optional first/last name (JWT required; not part of OTP signup)."""
    user_id = str(claims["sub"])
    updated = await user_repo.update_profile_by_id(
        user_id,
        first_name=payload.first_name,
        last_name=payload.last_name,
    )
    if not updated:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="User not found")
    changed = payload.first_name is not None or payload.last_name is not None
    return UpdateProfileResponse(
        success=True,
        message="Profile updated" if changed else "Profile unchanged",
        user_id=updated["_id"],
        email=updated["email"],
        first_name=updated.get("first_name") or "",
        last_name=updated.get("last_name") or "",
        last_login_at=updated.get("last_login_at"),
    )
