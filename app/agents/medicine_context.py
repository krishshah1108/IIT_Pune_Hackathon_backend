"""Shared serialization of vision `medicines[]` for LLM prompts (literacy, food)."""

from __future__ import annotations

from typing import Any


def build_medicine_rows_for_prompt(medicines: list[Any]) -> list[dict[str, Any]]:
    """One row per medicine with name + fields from vision; skips invalid or nameless entries."""
    out: list[dict[str, Any]] = []
    for med in medicines:
        if not isinstance(med, dict):
            continue
        name = str(med.get("name", "")).strip()
        if not name:
            continue
        row: dict[str, Any] = {
            "name": name,
            "dosage_pattern": med.get("dosage_pattern"),
            "duration_days": med.get("duration_days"),
            "instructions": med.get("instructions"),
            "confidence": med.get("confidence"),
            "reminder_times_24h": med.get("reminder_times_24h"),
        }
        if "name_legible" in med:
            row["name_legible"] = med.get("name_legible")
        out.append(row)
    return out
