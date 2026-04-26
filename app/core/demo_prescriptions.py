"""Demo-mode prescription shortcuts (no LLM calls). Maps accounts by email to fixed prescription ids."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any

from app.utils.normalization import normalize_dosage_pattern
from app.utils.reminder_times import coerce_reminder_times_24h


def _normalize_demo_email(email: str) -> str:
    return str(email).strip().lower()


# Login email (normalized) -> existing prescription `_id` for demo uploads (must exist in Mongo for that user).
DEMO_EMAIL_PRESCRIPTION_IDS: dict[str, str] = {
    "karmaa1008@gmail.com": "prx_f8f19cdca75b4c04a2b8a082a8630daf",
    "devanshupardeshi21@gmail.com": "prx_38cc9bb4428c49e0a5f44598fd746472",
    # Common typo from registration / JWT; same mapping as gmail.com
    "devanshupardeshi21@gmailc.om": "prx_38cc9bb4428c49e0a5f44598fd746472",
    "krishhshah1108@gmail.com": "prx_7597bc7a1a5a4737820038c805c4747d",
}

# Per-account draft lines: (name, dosage_pattern, duration_days, instructions_or_None)
DEMO_EMAIL_VISION_ROWS: dict[str, list[tuple[str, str, int, str | None]]] = {
    "karmaa1008@gmail.com": [
        ("Amoxicillin 625mg", "1-1-1", 10, "With plenty of water"),
        ("Paracetamol 650mg", "0-0-1", 5, "If fever or pain"),
    ],
    "devanshupardeshi21@gmail.com": [
        ("Azithromycin 500mg", "1-0-0", 5, "Complete the full course"),
        ("Pantoprazole 40mg", "1-0-0", 14, "Before breakfast"),
    ],
    "devanshupardeshi21@gmailc.om": [
        ("Azithromycin 500mg", "1-0-0", 5, "Complete the full course"),
        ("Pantoprazole 40mg", "1-0-0", 14, "Before breakfast"),
    ],
    "krishhshah1108@gmail.com": [
        ("Paracetamol 500mg", "1-0-1", 7, "After food"),
        ("Vitamin D3 60k IU", "1-0-0", 4, "Once weekly as labeled"),
    ],
}


def demo_prescription_id_for_email(email: str) -> str | None:
    """Return the fixed prescription id for demo uploads, or None if this email is not mapped."""
    return DEMO_EMAIL_PRESCRIPTION_IDS.get(_normalize_demo_email(email))


def _vision_medicine_row(
    name: str,
    raw_pattern: str,
    duration_days: int,
    instructions: str | None,
) -> dict[str, Any]:
    pattern = normalize_dosage_pattern(raw_pattern)
    times = coerce_reminder_times_24h(None, pattern)
    return {
        "name": name,
        "dosage_pattern": pattern,
        "duration_days": int(duration_days),
        "instructions": instructions,
        "confidence": 0.91,
        "reminder_times_24h": times,
        "name_legible": True,
    }


def build_demo_ai_output_for_email(language: str, email: str) -> dict[str, Any]:
    """
    Full `analysis` object matching the orchestrator shape (`vision` / `literacy` / `food`).
    Keyed by normalized login email so drafts match the account regardless of `usr_*` id.
    """
    _ = language
    key = _normalize_demo_email(email)
    rows = DEMO_EMAIL_VISION_ROWS.get(key)
    if not rows:
        rows = [
            ("Paracetamol 500mg", "1-0-1", 7, "As directed"),
        ]

    medicines = [_vision_medicine_row(n, p, d, ins) for n, p, d, ins in rows]
    names = [m["name"] for m in medicines]

    vision: dict[str, Any] = {
        "status": "ok",
        "medicines": medicines,
        "confidence": min(0.99, max(float(m["confidence"]) for m in medicines)),
        "partial": False,
    }

    literacy_items = [
        {
            "name": n,
            "explanation": "- Often used as your doctor advised.\n- Helps your body recover.\n- Use as doctor advised.",
        }
        for n in names
    ]
    literacy: dict[str, Any] = {"status": "ok", "items": literacy_items, "confidence": 0.84}

    food_items = [
        {
            "name": n,
            "advice": "- Eat: With or after food if your label says so.\n- Avoid: Alcohol unless your doctor approves.\n- Note: Ask your pharmacist when unsure.",
        }
        for n in names
    ]
    food: dict[str, Any] = {"status": "ok", "items": food_items, "confidence": 0.81}

    return {
        "vision": vision,
        "literacy": literacy,
        "food": food,
        "draft_ready_at": datetime.now(timezone.utc).isoformat(),
        "demo_mode": True,
    }
