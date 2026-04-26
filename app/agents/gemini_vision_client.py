"""Gemini-based prescription vision extractor (image + structured JSON)."""

from __future__ import annotations

import base64
from typing import Any

import httpx

from app.agents.gemini_client import GeminiTextClient
from app.core.config import get_settings


_VISION_SCHEMA: dict[str, Any] = {
    "type": "object",
    "properties": {
        "status": {"type": "string", "enum": ["ok", "failed"]},
        "partial": {"type": "boolean"},
        "confidence": {"type": "number"},
        "medicines": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "name": {"type": "string"},
                    "name_legible": {"type": "boolean"},
                    "dosage_pattern": {"type": "string"},
                    "duration_days": {"type": "integer"},
                    "instructions": {"type": "string"},
                    "confidence": {"type": "number"},
                    "reminder_times_24h": {"type": "array", "items": {"type": "string"}},
                },
                "required": [
                    "name",
                    "name_legible",
                    "dosage_pattern",
                    "duration_days",
                    "confidence",
                    "reminder_times_24h",
                ],
            },
        },
    },
    "required": ["status", "partial", "confidence", "medicines"],
}


class GeminiVisionClient:
    """Gemini multimodal client for prescription extraction."""

    def __init__(self, gemini: GeminiTextClient | None = None) -> None:
        settings = get_settings()
        self._gemini = gemini if gemini is not None else GeminiTextClient(model_name=settings.gemini_vision_model)

    async def extract_prescription(self, payload: dict[str, Any]) -> dict[str, Any]:
        if not self._gemini.enabled:
            raise ValueError("GOOGLE_API_KEY is required for vision extraction")

        language = str(payload.get("language", "en")).strip() or "en"
        parts = await self._build_parts(payload)
        if not parts:
            raise ValueError("image_url or image_base64 is required")

        system = (
            "You are a strict prescription OCR extractor. Output only structured JSON that matches the provided schema."
        )
        user = (
            "Extract medicines from the prescription image only.\n"
            "Never invent medicines.\n"
            "Copy visible text as closely as possible.\n"
            "If uncertain, lower confidence and set partial=true.\n"
            "Use status='failed' only when no medicine row is visible.\n"
            f"Language hint: {language}."
        )
        request_parts = [{"text": user}, *parts]
        parsed = await self._gemini.generate_json_from_parts(
            parts=request_parts,
            system_instruction=system,
            response_schema=_VISION_SCHEMA,
        )
        return self._normalize_response(parsed)

    async def _build_parts(self, payload: dict[str, Any]) -> list[dict[str, Any]]:
        image_url = str(payload.get("image_url", "")).strip()
        image_base64 = str(payload.get("image_base64", "")).strip()

        if image_base64:
            mime, raw_b64 = self._split_mime_and_data(image_base64)
            return [{"inline_data": {"mime_type": mime, "data": raw_b64}}]

        if image_url:
            timeout = httpx.Timeout(connect=20.0, read=45.0, write=20.0, pool=20.0)
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                res = await client.get(image_url)
                res.raise_for_status()
            content_type = (res.headers.get("content-type", "image/jpeg") or "image/jpeg").split(";")[0].strip().lower()
            if content_type == "image/jpg":
                content_type = "image/jpeg"
            if content_type not in {"image/jpeg", "image/png", "image/webp"}:
                content_type = "image/jpeg"
            raw_b64 = base64.b64encode(res.content).decode("ascii")
            return [{"inline_data": {"mime_type": content_type, "data": raw_b64}}]

        return []

    @staticmethod
    def _split_mime_and_data(value: str) -> tuple[str, str]:
        if value.startswith("data:"):
            header, data = value.split(",", 1)
            mime = header.replace("data:", "").replace(";base64", "").strip() or "image/jpeg"
            return mime, data.strip()
        if ";base64," in value:
            mime, data = value.split(";base64,", 1)
            return (mime.strip() or "image/jpeg"), data.strip()
        return "image/jpeg", value

    @staticmethod
    def _normalize_response(parsed: dict[str, Any]) -> dict[str, Any]:
        status = str(parsed.get("status", "")).strip().lower()
        out_status = "ok" if status in {"ok", "success", "completed"} else "failed"
        meds = parsed.get("medicines")
        medicines = meds if isinstance(meds, list) else []
        partial = bool(parsed.get("partial", False))
        try:
            confidence = float(parsed.get("confidence", 0.0))
        except (TypeError, ValueError):
            confidence = 0.0
        confidence = max(0.0, min(1.0, confidence))
        if not medicines and out_status == "ok":
            out_status = "failed"
            partial = True
        return {
            "status": out_status,
            "partial": partial,
            "confidence": confidence,
            "medicines": medicines,
        }
