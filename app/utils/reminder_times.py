"""24h reminder time helpers for prescription medicines."""

import re
from typing import Any

from app.utils.normalization import parse_frequency

_HHMM = re.compile(r"^(?:[01]\d|2[0-3]):[0-5]\d$")

# Waking-hour spaced defaults when LLM omits times (frontend can override).
_DEFAULTS_BY_FREQ: dict[int, list[str]] = {
    1: ["09:00"],
    2: ["09:00", "21:00"],
    3: ["08:00", "14:00", "20:00"],
    4: ["08:00", "12:00", "16:00", "20:00"],
    5: ["07:00", "10:00", "14:00", "18:00", "21:00"],
    6: ["08:00", "11:00", "14:00", "17:00", "20:00", "23:00"],
}


def parse_hhmm_list(raw: Any) -> list[str]:
    """Return valid HH:MM strings from a loose JSON/list input."""
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        s = str(item).strip()
        if _HHMM.match(s):
            out.append(s)
    return out


def default_reminder_times_24h(dosage_pattern: str) -> list[str]:
    """Infer spaced 24h clock times from normalized dosage frequency."""
    freq = max(1, min(6, parse_frequency(dosage_pattern)))
    return list(_DEFAULTS_BY_FREQ.get(freq, _DEFAULTS_BY_FREQ[3]))


def coerce_reminder_times_24h(raw: Any, dosage_pattern: str) -> list[str]:
    """Use LLM-supplied times when present; otherwise use frequency-based defaults from dosage_pattern."""
    parsed = parse_hhmm_list(raw)
    if parsed:
        return parsed
    return default_reminder_times_24h(dosage_pattern)
