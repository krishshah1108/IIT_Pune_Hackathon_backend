"""
Demo mode: JWT `sub` (user id) -> fixed prescription `_id` to return on upload without AI or new rows.

The mapping uses **only** `Authorization: Bearer …` claim `sub`. If Postman still shows another
user's `user_id` / `prescription_id`, the token is for a different account (decode at jwt.io).
"""

# When DEMO_MODE is on, `/prescriptions/upload` for these JWT `sub` values returns the listed
# existing Mongo prescription as-is (same response shape as production). No Cloudinary, no Gemini.
DEMO_USER_PRESCRIPTION_IDS: dict[str, str] = {
    # Demo user 1
    "usr_ba4421da515b45779ca96f4883a2ebca": "prx_7597bc7a1a5a4737820038c805c4747d",
    # Demo user 2
    "usr_3f78db297c3c470aac08b4559d7afd4c": "prx_38cc9bb4428c49e0a5f44598fd746472",
    # Demo user 3
    "usr_112cceaf03094e049c9cbb58e61aa097": "prx_f8f19cdca75b4c04a2b8a082a8630daf",
}


def demo_prescription_id_for_user(user_id: str) -> str | None:
    """Return the fixed prescription id for demo uploads, or None if this user is not mapped."""
    return DEMO_USER_PRESCRIPTION_IDS.get(str(user_id).strip())
