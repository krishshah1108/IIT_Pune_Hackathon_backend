"""Security and token utilities."""

import hashlib
import hmac
import secrets
from datetime import datetime, timedelta, timezone


def generate_otp(length: int = 6) -> str:
    """Generate numeric OTP."""
    digits = "0123456789"
    return "".join(secrets.choice(digits) for _ in range(length))


def hash_otp(otp: str) -> str:
    """Hash OTP before persistence."""
    return hashlib.sha256(otp.encode("utf-8")).hexdigest()


def verify_otp(plain_otp: str, hashed_otp: str) -> bool:
    """Verify OTP hash in constant time."""
    return hmac.compare_digest(hash_otp(plain_otp), hashed_otp)


def utc_now() -> datetime:
    """UTC timestamp helper."""
    return datetime.now(timezone.utc)


def utc_plus_minutes(minutes: int) -> datetime:
    """UTC helper for expiry creation."""
    return utc_now() + timedelta(minutes=minutes)
