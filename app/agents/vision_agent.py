"""Vision agent for prescription extraction."""

import base64
from typing import Any

from app.agents.base import Agent
from app.agents.gemini_vision_client import GeminiVisionClient
from app.utils.normalization import normalize_dosage_pattern
from app.utils.reminder_times import coerce_reminder_times_24h


class VisionAgent(Agent):
    """Extract medicines from prescription image."""

    def __init__(self, vision_client: GeminiVisionClient):
        self.vision_client = vision_client

    async def run(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Return structured medicine extraction output."""
        image_url = str(payload.get("image_url", "")).strip()
        image_b64 = payload.get("image_base64", "")

        if image_url:
            if not image_url.startswith("https://"):
                result = {
                    "status": "failed",
                    "error": "invalid_image_url",
                    "medicines": [],
                    "confidence": 0.0,
                    "partial": True,
                }
                return result
            vision_payload = {"image_url": image_url, "language": payload.get("language", "en")}
        else:
            if len(image_b64) < 40 or not self._is_valid_base64(str(image_b64)):
                result = {
                    "status": "failed",
                    "error": "blurry_or_invalid_image",
                    "medicines": [],
                    "confidence": 0.0,
                    "partial": True,
                }
                return result
            vision_payload = {"image_base64": image_b64, "language": payload.get("language", "en")}

        source = await self.vision_client.extract_prescription(vision_payload)
        source_medicines = source.get("medicines", [])
        normalized = []
        for row in source_medicines:
            if not isinstance(row, dict):
                continue
            name = str(row.get("name", "")).strip()
            pattern = str(row.get("dosage_pattern", "")).strip()
            if not name or not pattern:
                continue
            canon = normalize_dosage_pattern(pattern)
            times = coerce_reminder_times_24h(row.get("reminder_times_24h"), canon)
            entry: dict[str, Any] = {
                "name": name,
                "dosage_pattern": canon,
                "duration_days": int(row.get("duration_days", 30)),
                "instructions": row.get("instructions"),
                "confidence": float(row.get("confidence", source.get("confidence", 0.6))),
                "reminder_times_24h": times,
            }
            if "name_legible" in row:
                entry["name_legible"] = bool(row.get("name_legible"))
            normalized.append(entry)

        if not normalized:
            result = {
                "status": "failed",
                "error": "partial_or_empty_extraction",
                "medicines": [],
                "confidence": float(source.get("confidence", 0.0)),
                "partial": True,
            }
            return result

        result = {
            "status": source.get("status", "ok"),
            "medicines": normalized,
            "confidence": min(0.99, float(source.get("confidence", 0.7))),
            "partial": bool(source.get("partial", False)),
        }
        return result

    def _is_valid_base64(self, image_base64: str) -> bool:
        """Validate basic base64 shape to avoid invalid upstream requests."""
        try:
            base64.b64decode(image_base64, validate=False)
            return True
        except Exception:
            return False
