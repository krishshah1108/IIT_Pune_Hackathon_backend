"""Demo-mode prescription shortcuts (no LLM calls). Maps specific users to fixed prescription ids."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.utils.normalization import normalize_dosage_pattern
from app.utils.reminder_times import coerce_reminder_times_24h

# JWT `sub` / user _id -> existing prescription _id to reuse for uploads (must exist in Mongo).
DEMO_USER_PRESCRIPTION_IDS: dict[str, str] = {
    "usr_ba4421da515b45779ca96f4883a2ebca": "prx_7597bc7a1a5a4737820038c805c4747d",
    "usr_3f78db297c3c470aac08b4559d7afd4c": "prx_38cc9bb4428c49e0a5f44598fd746472",
    "usr_112cceaf03094e049c9cbb58e61aa097": "prx_f8f19cdca75b4c04a2b8a082a8630daf",
}


def demo_prescription_id_for_user(user_id: str) -> str | None:
    """Return the fixed prescription id for demo uploads, or None if this user is not mapped."""
    return DEMO_USER_PRESCRIPTION_IDS.get(user_id)


def _primary_medicine_for_prescription(prescription_id: str) -> dict[str, Any]:
    """Pick a plausible demo line per prx_* so the three accounts do not look identical."""
    defaults: dict[str, tuple[str, str, int]] = {
        "prx_7597bc7a1a5a4737820038c805c4747d": ("Paracetamol 500mg", "1-0-1", 7),
        "prx_38cc9bb4428c49e0a5f44598fd746472": ("Azithromycin 500mg", "1-0-0", 5),
        "prx_f8f19cdca75b4c04a2b8a082a8630daf": ("Amoxicillin 625mg", "1-1-1", 10),
    }
    name, raw_pattern, duration = defaults.get(
        prescription_id,
        ("Paracetamol 500mg", "1-0-1", 7),
    )
    pattern = normalize_dosage_pattern(raw_pattern)
    times = coerce_reminder_times_24h(None, pattern)
    return {
        "name": name,
        "dosage_pattern": pattern,
        "duration_days": duration,
        "instructions": "As directed on the prescription",
        "confidence": 0.91,
        "reminder_times_24h": times,
        "name_legible": True,
    }


def build_demo_ai_output(language: str, prescription_id: str) -> dict[str, Any]:
    """Structured draft matching orchestrator shape (`vision` / `literacy` / `food`)."""
    _ = language  # tone hint for future i18n strings
    med = _primary_medicine_for_prescription(prescription_id)
    name = med["name"]
    vision: dict[str, Any] = {
        "status": "ok",
        "medicines": [med],
        "confidence": float(med["confidence"]),
        "partial": False,
    }
    literacy: dict[str, Any] = {
        "status": "ok",
        "items": [
            {
                "name": name,
                "explanation": "- Often used as your doctor advised.\n- Helps your body recover.\n- Use as doctor advised.",
            }
        ],
        "confidence": 0.84,
    }
    food: dict[str, Any] = {
        "status": "ok",
        "items": [
            {
                "name": name,
                "advice": "- Eat: With or after food if your label says so.\n- Avoid: Alcohol unless your doctor approves.\n- Note: Ask your pharmacist when unsure.",
            }
        ],
        "confidence": 0.81,
    }
    return {
        "vision": vision,
        "literacy": literacy,
        "food": food,
        "draft_ready_at": datetime.now(timezone.utc).isoformat(),
        "demo_mode": True,
    }
