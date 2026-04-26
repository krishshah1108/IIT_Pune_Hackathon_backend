"""User profile schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class UpdateProfileRequest(BaseModel):
    """Update display name fields; caller is identified by JWT (Bearer)."""

    first_name: str | None = Field(default=None, max_length=120)
    last_name: str | None = Field(default=None, max_length=120)

    @field_validator("first_name", "last_name", mode="before")
    @classmethod
    def normalize_name(cls, value: object) -> str | None:
        if value is None:
            return None
        s = str(value).strip()
        return s[:120]


class UpdateProfileResponse(BaseModel):
    """Profile update success payload."""

    success: bool
    message: str
    user_id: str
    email: EmailStr
    first_name: str
    last_name: str
    last_login_at: datetime | None = None


class ProfileResponse(BaseModel):
    """Current user profile (GET /users/profile)."""

    user_id: str
    email: EmailStr
    first_name: str
    last_name: str
    last_login_at: datetime | None = None
