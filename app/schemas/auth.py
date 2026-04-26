"""Authentication schemas."""

from datetime import datetime
from pydantic import BaseModel, EmailStr, Field, field_validator


class RequestOTPRequest(BaseModel):
    """Request OTP by email."""

    email: EmailStr


class RequestOTPResponse(BaseModel):
    """OTP request response."""

    success: bool
    message: str
    resend_after_seconds: int


class VerifyOTPRequest(BaseModel):
    """Verify OTP payload."""

    email: EmailStr
    otp: str = Field(min_length=4, max_length=8)

    @field_validator("otp")
    @classmethod
    def otp_numeric(cls, value: str) -> str:
        """Validate OTP format."""
        if not value.isdigit():
            raise ValueError("OTP must be numeric")
        return value


class AuthUser(BaseModel):
    """Authenticated user output."""

    user_id: str
    email: EmailStr
    first_name: str = ""
    last_name: str = ""
    last_login_at: datetime | None = None


class VerifyOTPResponse(BaseModel):
    """OTP verification response."""

    success: bool
    message: str
    is_new_user: bool
    user: AuthUser
    access_token: str
    token_type: str = "bearer"
