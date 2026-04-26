"""OTP auth service."""

import logging
from datetime import datetime, timezone

from app.core.config import get_settings
from app.core.jwt_tokens import issue_access_token
from app.core.exceptions import ConflictError, NotFoundError, UnauthorizedError, ValidationError
from app.core.security import generate_otp, hash_otp, utc_plus_minutes, verify_otp
from app.repositories.otp_repository import OTPRepository
from app.repositories.user_repository import UserRepository
from app.utils.email import EmailClient

logger = logging.getLogger(__name__)


def _as_utc_aware(dt: datetime) -> datetime:
    """Normalize datetimes from MongoDB (often naive UTC) for comparisons."""
    if dt.tzinfo is None:
        return dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(timezone.utc)


class OTPService:
    """Handle email OTP request and verification."""

    def __init__(self, otp_repo: OTPRepository, user_repo: UserRepository, email_client: EmailClient):
        self.otp_repo = otp_repo
        self.user_repo = user_repo
        self.email_client = email_client
        self.settings = get_settings()

    async def _enforce_rate_limits(self, email: str) -> None:
        """Hourly OTP cap across request and resend."""
        recent_count = await self.otp_repo.count_recent_requests(email)
        if recent_count >= self.settings.otp_requests_per_hour:
            raise ValidationError("Too many OTP requests. Please try again later.")

    def _enforce_resend_cooldown(self, latest: dict | None) -> None:
        """Require cooldown since last OTP session creation."""
        if not latest:
            return
        delta = datetime.now(timezone.utc) - _as_utc_aware(latest["created_at"])
        if delta.total_seconds() < self.settings.otp_resend_cooldown_seconds:
            cooldown = self.settings.otp_resend_cooldown_seconds - int(delta.total_seconds())
            raise ValidationError(f"OTP recently sent. Retry after {cooldown} seconds.")

    async def _create_and_deliver_otp(self, email: str, log_action: str) -> dict:
        """Create OTP session, send email, return API payload."""
        otp = generate_otp()
        session = await self.otp_repo.create_session(
            email=email,
            otp_hash=hash_otp(otp),
            expires_at=utc_plus_minutes(self.settings.otp_expiry_minutes),
        )
        await self.email_client.send_email(
            to_email=email,
            subject="MediReminder OTP",
            body=f"Your OTP is {otp}. It expires in {self.settings.otp_expiry_minutes} minutes.",
        )
        logger.info("%s email=%s session_id=%s", log_action, email, session["_id"])
        return {"success": True, "resend_after_seconds": self.settings.otp_resend_cooldown_seconds}

    async def request_otp(self, email: str) -> dict:
        """Request OTP with throttling and cooldown."""
        await self._enforce_rate_limits(email)
        latest = await self.otp_repo.get_latest(email)
        self._enforce_resend_cooldown(latest)
        payload = await self._create_and_deliver_otp(email, "otp.requested")
        payload["message"] = "OTP sent"
        return payload

    async def resend_otp(self, email: str) -> dict:
        """Resend OTP only when the latest session exists and is not yet verified."""
        await self._enforce_rate_limits(email)
        latest = await self.otp_repo.get_latest(email)
        if not latest:
            raise NotFoundError("No OTP session found. Request a code first using /auth/otp/request.")
        if latest.get("verified"):
            raise ConflictError("OTP already verified. Request a new code using /auth/otp/request.")
        self._enforce_resend_cooldown(latest)
        payload = await self._create_and_deliver_otp(email, "otp.resent")
        payload["message"] = "OTP resent"
        return payload

    async def verify_otp(self, email: str, otp: str) -> dict:
        """Verify OTP, upsert user, and return user payload."""
        session = await self.otp_repo.get_latest(email)
        if not session:
            raise UnauthorizedError("OTP session not found")
        if session["verified"]:
            raise UnauthorizedError("OTP already used")
        if datetime.now(timezone.utc) > _as_utc_aware(session["expires_at"]):
            raise UnauthorizedError("OTP expired")
        if session["attempts"] >= self.settings.otp_max_attempts:
            raise UnauthorizedError("Max OTP attempts exceeded")

        if not verify_otp(otp, session["otp_hash"]):
            await self.otp_repo.mark_attempt(session["_id"])
            raise UnauthorizedError("Invalid OTP")

        await self.otp_repo.mark_verified(session["_id"])
        existing = await self.user_repo.get_by_email(email)
        is_new = existing is None
        if is_new:
            existing = await self.user_repo.create_user(email)
        else:
            await self.user_repo.touch_login(existing["_id"])

        access_token = issue_access_token(user_id=existing["_id"], email=existing["email"])
        return {
            "success": True,
            "message": "Authenticated",
            "is_new_user": is_new,
            "user": {
                "user_id": existing["_id"],
                "email": existing["email"],
                "first_name": existing.get("first_name") or "",
                "last_name": existing.get("last_name") or "",
                "last_login_at": existing.get("last_login_at"),
            },
            "access_token": access_token,
            "token_type": "bearer",
        }
