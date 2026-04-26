"""Shared helpers for literacy/food Gemini JSON agents."""

from __future__ import annotations

import json
import logging
from typing import Any, Literal

from app.agents.gemini_client import GeminiTextClient
from app.agents.medicine_context import build_medicine_rows_for_prompt

logger = logging.getLogger(__name__)

ItemValueKey = Literal["explanation", "advice"]


def enrichment_failed(error: str) -> dict[str, Any]:
    return {"status": "failed", "items": [], "confidence": 0.0, "error": error}


def parse_enrichment_items(
    parsed: dict[str, Any],
    *,
    value_key: ItemValueKey,
    max_confidence: float,
    default_conf: float,
) -> dict[str, Any]:
    if parsed.get("status") != "ok":
        raise ValueError("enrichment status not ok")
    raw = parsed.get("items")
    if not isinstance(raw, list):
        raise ValueError("enrichment items not a list")
    items: list[dict[str, str]] = []
    for it in raw:
        if not isinstance(it, dict):
            continue
        name = str(it.get("name", "")).strip()
        value = str(it.get(value_key, "")).strip()
        if name and value:
            items.append({"name": name, value_key: value})
    if not items:
        raise ValueError("enrichment empty items")
    conf = float(parsed.get("confidence", default_conf))
    return {"status": "ok", "items": items, "confidence": min(max_confidence, conf)}


async def run_gemini_enrichment(
    gemini: GeminiTextClient,
    payload: dict[str, Any],
    *,
    system: str,
    user_template: str,
    value_key: ItemValueKey,
    log_name: str,
    max_confidence: float,
    default_conf: float,
) -> dict[str, Any]:
    """One Gemini round-trip: vision medicines → JSON items with `value_key` per name."""
    meds = payload.get("medicines", [])
    rows = build_medicine_rows_for_prompt(meds)
    if not rows:
        return enrichment_failed("no_medicines")
    if not gemini.enabled:
        return enrichment_failed("gemini_not_configured")

    language = str(payload.get("language", "en")).strip() or "en"
    user_prompt = user_template.format(
        language=language,
        meds_json=json.dumps(rows, ensure_ascii=False),
    )
    schema: dict[str, Any] = {
        "type": "object",
        "properties": {
            "status": {"type": "string", "enum": ["ok", "failed"]},
            "items": {
                "type": "array",
                "items": {
                    "type": "object",
                    "properties": {
                        "name": {"type": "string"},
                        value_key: {"type": "string"},
                    },
                    "required": ["name", value_key],
                },
            },
            "confidence": {"type": "number"},
        },
        "required": ["status", "items", "confidence"],
    }

    try:
        parsed = await gemini.generate_json(
            user_prompt,
            system_instruction=system,
            response_schema=schema,
        )
        return parse_enrichment_items(
            parsed,
            value_key=value_key,
            max_confidence=max_confidence,
            default_conf=default_conf,
        )
    except Exception:
        logger.exception(log_name)
        return enrichment_failed("gemini_failed")
