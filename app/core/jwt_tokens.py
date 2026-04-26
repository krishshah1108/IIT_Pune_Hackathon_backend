"""JWT access tokens (HS256)."""

from datetime import datetime, timedelta, timezone
from typing import Any

import jwt
from jwt.exceptions import InvalidTokenError

from app.core.config import get_settings


def issue_access_token(*, user_id: str, email: str) -> str:
    """Mint a short-lived access JWT after OTP verify."""
    settings = get_settings()
    now = datetime.now(timezone.utc)
    exp = now + timedelta(minutes=settings.jwt_access_expire_minutes)
    payload: dict[str, Any] = {
        "sub": user_id,
        "email": str(email),
        "type": "access",
        "iat": int(now.timestamp()),
        "exp": int(exp.timestamp()),
    }
    return jwt.encode(payload, settings.jwt_secret_key, algorithm=settings.jwt_algorithm)


def decode_access_token(token: str) -> dict[str, Any]:
    """Validate JWT and return claims (sub, email, …). Raises jwt exceptions on failure."""
    settings = get_settings()
    payload = jwt.decode(
        token,
        settings.jwt_secret_key,
        algorithms=[settings.jwt_algorithm],
    )
    if payload.get("type") != "access":
        raise InvalidTokenError("Wrong token type")
    if not payload.get("sub") or not payload.get("email"):
        raise InvalidTokenError("Missing claims")
    return payload
