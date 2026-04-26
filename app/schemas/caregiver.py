"""Caregiver Pydantic schemas."""

from datetime import datetime

from pydantic import BaseModel, EmailStr, Field, field_validator


class CaregiverBaseResponse(BaseModel):
    """Common caregiver fields in responses."""

    caregiver_id: str
    user_id: str
    display_name: str
    email: str
    phone: str | None
    relationship_label: str | None
    is_active: bool
    notify_on_missed_dose: bool
    created_at: datetime
    updated_at: datetime

    @classmethod
    def from_doc(cls, doc: dict) -> "CaregiverBaseResponse":
        return cls(
            caregiver_id=doc["_id"],
            user_id=doc["user_id"],
            display_name=doc["display_name"],
            email=doc["email"],
            phone=doc.get("phone"),
            relationship_label=doc.get("relationship_label"),
            is_active=bool(doc.get("is_active", True)),
            notify_on_missed_dose=bool(doc.get("notify_on_missed_dose", True)),
            created_at=doc["created_at"],
            updated_at=doc["updated_at"],
        )


class CreateCaregiverRequest(BaseModel):
    display_name: str = Field(..., min_length=1, max_length=200)
    email: EmailStr
    phone: str | None = Field(default=None, max_length=32)
    relationship_label: str | None = Field(default=None, max_length=80)
    is_active: bool = True
    notify_on_missed_dose: bool = True

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_name(cls, v: object) -> str:
        return str(v).strip()[:200]

    @field_validator("relationship_label", "phone", mode="before")
    @classmethod
    def strip_opt(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class UpdateCaregiverRequest(BaseModel):
    display_name: str | None = Field(default=None, min_length=1, max_length=200)
    email: EmailStr | None = None
    phone: str | None = Field(default=None, max_length=32)
    relationship_label: str | None = Field(default=None, max_length=80)
    is_active: bool | None = None
    notify_on_missed_dose: bool | None = None

    @field_validator("display_name", mode="before")
    @classmethod
    def strip_name_u(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()[:200]
        return s if s else None

    @field_validator("relationship_label", "phone", mode="before")
    @classmethod
    def strip_opt_u(cls, v: object) -> str | None:
        if v is None:
            return None
        s = str(v).strip()
        return s if s else None


class CaregiverListResponse(BaseModel):
    success: bool = True
    items: list[CaregiverBaseResponse]


class CaregiverSingleResponse(BaseModel):
    success: bool = True
    item: CaregiverBaseResponse


class DeleteCaregiverResponse(BaseModel):
    success: bool = True
    message: str
    caregiver_id: str
