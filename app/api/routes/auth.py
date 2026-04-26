"""Auth routes."""

from fastapi import APIRouter, Depends, HTTPException, status

from app.api.dependencies import get_otp_service
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from app.schemas.auth import RequestOTPRequest, RequestOTPResponse, VerifyOTPRequest, VerifyOTPResponse
from app.services.otp_service import OTPService

router = APIRouter(prefix="/auth", tags=["auth"])


@router.post("/otp/request", response_model=RequestOTPResponse)
async def request_otp(payload: RequestOTPRequest, otp_service: OTPService = Depends(get_otp_service)) -> RequestOTPResponse:
    """Request OTP for email authentication."""
    try:
        result = await otp_service.request_otp(payload.email)
        return RequestOTPResponse(**result)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc


@router.post("/otp/resend", response_model=RequestOTPResponse)
async def resend_otp(payload: RequestOTPRequest, otp_service: OTPService = Depends(get_otp_service)) -> RequestOTPResponse:
    """Resend OTP for an active (unverified) session after cooldown."""
    try:
        result = await otp_service.resend_otp(payload.email)
        return RequestOTPResponse(**result)
    except ValidationError as exc:
        raise HTTPException(status_code=status.HTTP_429_TOO_MANY_REQUESTS, detail=str(exc)) from exc
    except NotFoundError as exc:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(exc)) from exc
    except ConflictError as exc:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(exc)) from exc


@router.post("/otp/verify", response_model=VerifyOTPResponse)
async def verify_otp(payload: VerifyOTPRequest, otp_service: OTPService = Depends(get_otp_service)) -> VerifyOTPResponse:
    """Verify OTP and authenticate user."""
    try:
        result = await otp_service.verify_otp(payload.email, payload.otp)
        return VerifyOTPResponse(**result)
    except UnauthorizedError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc
