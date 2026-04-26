"""Application configuration module."""

from functools import lru_cache
from typing import Any

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime settings loaded from environment."""

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8", extra="ignore")

    app_name: str = Field(default="MediReminder Backend", alias="APP_NAME")
    app_env: str = Field(default="development", alias="APP_ENV")
    app_host: str = Field(default="0.0.0.0", alias="APP_HOST")
    app_port: int = Field(default=8000, alias="APP_PORT")
    app_log_level: str = Field(default="INFO", alias="APP_LOG_LEVEL")
    # When true, mapped demo users skip Gemini on prescription upload (see `app.core.demo_prescriptions`).
    demo_mode: bool = Field(default=False, alias="DEMO_MODE")

    @field_validator("demo_mode", mode="before")
    @classmethod
    def parse_demo_mode(cls, v: Any) -> bool:
        if isinstance(v, bool):
            return v
        if v is None or v == "":
            return False
        s = str(v).strip().lower()
        return s in ("on", "1", "true", "yes", "onn")
    # Max characters of v0/Gemini raw assistant text to log; 0 = log length only (no body).
    llm_response_log_max_chars: int = Field(default=8000, alias="LLM_RESPONSE_LOG_MAX_CHARS")

    mongo_uri: str = Field(alias="MONGO_URI")
    mongo_db_name: str = Field(alias="MONGO_DB_NAME")

    otp_expiry_minutes: int = Field(default=10, alias="OTP_EXPIRY_MINUTES")
    otp_max_attempts: int = Field(default=5, alias="OTP_MAX_ATTEMPTS")
    otp_resend_cooldown_seconds: int = Field(default=60, alias="OTP_RESEND_COOLDOWN_SECONDS")
    otp_requests_per_hour: int = Field(default=10, alias="OTP_REQUESTS_PER_HOUR")

    smtp_host: str = Field(default="smtp.gmail.com", alias="SMTP_HOST")
    smtp_port: int = Field(default=587, alias="SMTP_PORT")
    smtp_user: str = Field(alias="SMTP_USER")
    smtp_pass: str = Field(alias="SMTP_PASS")
    email_from: str = Field(alias="EMAIL_FROM")
    smtp_timeout_seconds: int = Field(default=20, alias="SMTP_TIMEOUT_SECONDS")
    smtp_starttls: bool = Field(default=True, alias="SMTP_STARTTLS")

    v0_api_base_url: str = Field(default="https://api.v0.dev", alias="V0_API_BASE_URL")
    v0_api_key: str = Field(default="", alias="V0_API_KEY")
    v0_model: str = Field(default="auto", alias="V0_MODEL")
    v0_timeout_seconds: int = Field(default=300, alias="V0_TIMEOUT_SECONDS")

    # Google Gemini (generateContent) for vision + literacy + food.
    google_api_key: str = Field(default="", alias="GOOGLE_API_KEY")
    gemini_api_base_url: str = Field(
        default="https://generativelanguage.googleapis.com/v1beta",
        alias="GEMINI_API_BASE_URL",
    )
    gemini_vision_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_VISION_MODEL")
    gemini_literacy_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_LITERACY_MODEL")
    gemini_food_model: str = Field(default="gemini-2.5-flash", alias="GEMINI_FOOD_MODEL")
    gemini_timeout_seconds: int = Field(default=90, alias="GEMINI_TIMEOUT_SECONDS")
    gemini_temperature: float = Field(default=0.35, alias="GEMINI_TEMPERATURE")
    gemini_max_output_tokens: int = Field(default=2048, alias="GEMINI_MAX_OUTPUT_TOKENS")

    cloudinary_cloud_name: str = Field(alias="CLOUDINARY_CLOUD_NAME")
    cloudinary_api_key: str = Field(alias="CLOUDINARY_API_KEY")
    cloudinary_api_secret: str = Field(alias="CLOUDINARY_API_SECRET")
    cloudinary_folder: str = Field(default="medi_reminder", alias="CLOUDINARY_FOLDER")
    max_prescription_upload_bytes: int = Field(default=15 * 1024 * 1024, alias="MAX_PRESCRIPTION_UPLOAD_BYTES")

    schedule_scan_interval_seconds: int = Field(default=60, alias="SCHEDULE_SCAN_INTERVAL_SECONDS")
    missed_dose_grace_minutes: int = Field(default=30, alias="MISSED_DOSE_GRACE_MINUTES")

    jwt_secret_key: str = Field(
        default="development-only-change-JWT_SECRET_KEY-in-production",
        alias="JWT_SECRET_KEY",
    )
    jwt_algorithm: str = Field(default="HS256", alias="JWT_ALGORITHM")
    jwt_access_expire_minutes: int = Field(default=10080, alias="JWT_ACCESS_EXPIRE_MINUTES")


@lru_cache(maxsize=1)
def get_settings() -> Settings:
    """Return cached settings instance."""
    return Settings()
