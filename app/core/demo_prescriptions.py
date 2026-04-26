"""
Demo mode: return an existing Mongo prescription on upload (no Cloudinary / Gemini).

Resolve the fixed `prx_*` by JWT `sub` first, then by JWT `email` (same three demo accounts).
"""

from __future__ import annotations

# JWT `sub` (users._id) -> prescription `_id` (must exist in Mongo for that user_id).
DEMO_USER_PRESCRIPTION_IDS: dict[str, str] = {
    "usr_ba4421da515b45779ca96f4883a2ebca": "prx_7597bc7a1a5a4737820038c805c4747d",
    "usr_3f78db297c3c470aac08b4559d7afd4c": "prx_38cc9bb4428c49e0a5f44598fd746472",
    "usr_112cceaf03094e049c9cbb58e61aa097": "prx_f8f19cdca75b4c04a2b8a082a8630daf",
}

# Same mapping by login email (normalized) if you ever need email-only resolution.
DEMO_EMAIL_PRESCRIPTION_IDS: dict[str, str] = {
    "krishhshah1108@gmail.com": "prx_7597bc7a1a5a4737820038c805c4747d",
    "devanshupardeshi21@gmail.com": "prx_38cc9bb4428c49e0a5f44598fd746472",
    "karmaa1008@gmail.com": "prx_f8f19cdca75b4c04a2b8a082a8630daf",
}


def demo_prescription_id_for_user(user_id: str) -> str | None:
    """Return fixed prescription id for this JWT `sub`, or None."""
    return DEMO_USER_PRESCRIPTION_IDS.get(str(user_id).strip())


def demo_prescription_id_for_claims(user_id: str, email: str | None) -> str | None:
    """
    Prefer `sub`; fall back to normalized `email` so OTP logins always hit the right prx_*
    even if ids were ever out of sync.
    """
    prx = demo_prescription_id_for_user(user_id)
    if prx:
        return prx
    if email:
        return DEMO_EMAIL_PRESCRIPTION_IDS.get(str(email).strip().lower())
    return None
