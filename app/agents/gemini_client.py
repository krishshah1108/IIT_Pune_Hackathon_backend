"""Async client for Google AI Gemini generateContent (REST)."""

from __future__ import annotations

import json
import logging
import time
import asyncio
from typing import Any

import httpx

from app.core.config import get_settings
from app.utils.json_utils import extract_json_object
from app.utils.llm_log import log_model_text
logger = logging.getLogger(__name__)
_LOG_BODY = 500


def _gemini_error_summary(data: Any) -> str:
    if not isinstance(data, dict):
        return "non_object_response"
    err = data.get("error")
    if isinstance(err, dict):
        return str(
            {
                "code": err.get("code"),
                "message": (err.get("message") or "")[:400],
                "status": err.get("status"),
            }
        )[:500]
    return str(data)[:_LOG_BODY]


class GeminiTextClient:
    """POST to `v1beta/models/{model}:generateContent` with API key (Google AI Studio / Gemini API)."""

    def __init__(self, *, model_name: str | None = None) -> None:
        self.settings = get_settings()
        self.model_name = (model_name or "").strip() or None

    @property
    def enabled(self) -> bool:
        return bool(self.settings.google_api_key.strip())

    async def generate_text(self, user_prompt: str, *, system_instruction: str | None = None) -> str:
        """Return first text part from model response."""
        return await self.generate_from_parts(
            parts=[{"text": user_prompt}],
            system_instruction=system_instruction,
        )

    async def generate_json(
        self,
        user_prompt: str,
        *,
        system_instruction: str | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate and parse strict JSON from text-only prompt."""
        return await self._generate_and_parse_json(
            parts=[{"text": user_prompt}],
            system_instruction=system_instruction,
            response_schema=response_schema,
        )

    async def generate_json_from_parts(
        self,
        *,
        parts: list[dict[str, Any]],
        system_instruction: str | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        """Generate and parse strict JSON from multimodal parts."""
        return await self._generate_and_parse_json(
            parts=parts,
            system_instruction=system_instruction,
            response_schema=response_schema,
        )

    async def _generate_and_parse_json(
        self,
        *,
        parts: list[dict[str, Any]],
        system_instruction: str | None,
        response_schema: dict[str, Any] | None,
    ) -> dict[str, Any]:
        """Generate JSON with one retry when model returns non-JSON text."""
        attempts = 2
        for attempt in range(1, attempts + 1):
            text = await self.generate_from_parts(
                parts=parts,
                system_instruction=system_instruction,
                response_mime_type="application/json",
                response_schema=response_schema,
            )
            try:
                return extract_json_object(text)
            except ValueError as exc:
                logger.warning("gemini.parse_failed attempt=%s reason=no_json_object", attempt)
                log_model_text(
                    logger,
                    "gemini.parse_failed.preview",
                    text,
                    int(self.settings.llm_response_log_max_chars),
                )
                if attempt >= attempts:
                    raise RuntimeError("Gemini returned non-JSON response") from exc
                await asyncio.sleep(0.35 * attempt)

        raise RuntimeError("Gemini JSON generation failed unexpectedly")

    async def generate_from_parts(
        self,
        *,
        parts: list[dict[str, Any]],
        system_instruction: str | None = None,
        response_mime_type: str | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> str:
        """Generate text from arbitrary Gemini content parts."""
        if not self.enabled:
            raise RuntimeError("GOOGLE_API_KEY is not set")

        base = self.settings.gemini_api_base_url.rstrip("/")
        model = (self.model_name or self.settings.gemini_vision_model).strip()
        url = f"{base}/models/{model}:generateContent"
        t0 = time.perf_counter()

        body: dict[str, Any] = {
            "contents": [{"role": "user", "parts": parts}],
            "generationConfig": {
                "temperature": self.settings.gemini_temperature,
                "maxOutputTokens": self.settings.gemini_max_output_tokens,
            },
        }
        if response_mime_type:
            body["generationConfig"]["responseMimeType"] = response_mime_type
        if response_schema is not None:
            # Use JSON Schema field for Gemini Developer API structured output.
            body["generationConfig"]["responseJsonSchema"] = response_schema
        if system_instruction:
            body["systemInstruction"] = {"parts": [{"text": system_instruction}]}

        timeout = httpx.Timeout(
            connect=30.0,
            read=float(self.settings.gemini_timeout_seconds),
            write=60.0,
            pool=30.0,
        )
        headers = {
            "x-goog-api-key": self.settings.google_api_key.strip(),
            "Content-Type": "application/json",
        }

        data: dict[str, Any] | None = None
        attempts = 3
        for attempt in range(1, attempts + 1):
            try:
                async with httpx.AsyncClient(timeout=timeout) as client:
                    response = await client.post(url, headers=headers, json=body)
                    ms = (time.perf_counter() - t0) * 1000.0
                    if not response.is_success:
                        try:
                            err_obj = response.json()
                        except json.JSONDecodeError:
                            err_obj = (response.text or "")[:_LOG_BODY]
                        j_err = _gemini_error_summary(err_obj) if isinstance(err_obj, dict) else str(err_obj)[:_LOG_BODY]
                        logger.error(
                            "gemini.failed reason=http_error status=%s duration_ms=%.0f error=%s",
                            response.status_code,
                            ms,
                            j_err,
                        )
                    response.raise_for_status()
                    try:
                        data = response.json()
                    except json.JSONDecodeError as exc:
                        raw = response.text[:_LOG_BODY] if response.text else ""
                        logger.error(
                            "gemini.failed reason=response_not_json duration_ms=%.0f preview=%s",
                            (time.perf_counter() - t0) * 1000.0,
                            raw,
                        )
                        raise RuntimeError("Gemini response was not valid JSON") from exc
                    break
            except (httpx.ReadError, httpx.ConnectError, httpx.RemoteProtocolError, httpx.TimeoutException) as exc:
                if attempt == attempts:
                    raise
                await asyncio.sleep(0.35 * attempt)
                logger.warning("gemini.retry attempt=%s reason=%s", attempt + 1, type(exc).__name__)

        if data is None:
            raise RuntimeError("Gemini request failed without response data")

        candidates = data.get("candidates") or []
        if not candidates:
            ms = (time.perf_counter() - t0) * 1000.0
            logger.error(
                "gemini.failed reason=no_candidates duration_ms=%.0f top_keys=%s",
                ms,
                list(data.keys()) if isinstance(data, dict) else type(data),
            )
            raise RuntimeError("Gemini returned no candidates")

        content = (candidates[0] or {}).get("content") or {}
        text_parts = content.get("parts") or []
        merged_parts: list[str] = []
        for p in text_parts:
            t = str(p.get("text", "")).strip()
            if t:
                merged_parts.append(t)
        if merged_parts:
            # Gemini can split one logical answer across multiple text parts.
            # Join all parts before JSON parsing to avoid accidental truncation.
            return "\n".join(merged_parts)

        ms = (time.perf_counter() - t0) * 1000.0
        logger.error("gemini.failed reason=empty_text duration_ms=%.0f", ms)
        raise RuntimeError("Gemini returned empty text")
