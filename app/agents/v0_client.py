"""v0 Platform API client — prescription vision via `POST /v1/chats` only."""

from __future__ import annotations

import json
import logging
import time
import base64
import re
from typing import Any

import httpx

from app.core.config import get_settings
from app.core.exceptions import RetryableAgentError, V0PaymentRequiredError
from app.utils.json_utils import extract_json_object

logger = logging.getLogger(__name__)

_V0_CHATS_PATH = "/v1/chats"
_LOG_TEXT_PREVIEW = 500


def _safe_error_summary(response_text: str) -> str:
    """One-line error from v0 JSON error body, or truncated raw text."""
    if not (response_text or "").strip():
        return "(empty body)"
    try:
        parsed = json.loads(response_text)
        if isinstance(parsed, dict) and "error" in parsed:
            return str(parsed.get("error"))[:300]
    except (json.JSONDecodeError, TypeError):
        pass
    return (response_text[:200] + "…") if len(response_text) > 200 else response_text


def _content_to_text(content: Any) -> str:
    if isinstance(content, str):
        return content.strip()
    if isinstance(content, list):
        parts: list[str] = []
        for part in content:
            if not isinstance(part, dict):
                continue
            if part.get("type") == "text":
                parts.append(str(part.get("text", "")))
        return "".join(parts).strip()
    return str(content or "").strip()


class V0Client:
    """`POST {V0_API_BASE_URL}/v1/chats` with a single `message` (text + image URL or data URL at the end)."""

    def __init__(self) -> None:
        self.settings = get_settings()

    async def extract_prescription(self, payload: dict[str, Any]) -> dict[str, Any]:
        """Call v0 chats create and return normalized extraction JSON."""
        if not self.settings.v0_api_key.strip():
            raise ValueError("V0_API_KEY is required for vision extraction")

        image_url = payload.get("image_url")
        image_base64 = payload.get("image_base64")
        if not image_url and not image_base64:
            raise ValueError("image_url or image_base64 is required")
        language = payload.get("language", "en")

        message = self._build_extraction_message(
            language=language,
            image_url=str(image_url).strip() if image_url else None,
            image_base64=image_base64 if image_base64 else None,
        )
        result = await self._request_once(request_payload={"message": message})
        if image_url and self._should_retry_with_data_url(result):
            data_url = await self._build_data_url_from_image_url(str(image_url).strip())
            if data_url:
                message = self._build_extraction_message(
                    language=language,
                    image_url=None,
                    image_base64=data_url,
                )
                return await self._request_once(request_payload={"message": message})
        if self._has_medicines(result):
            consensus = await self._extract_strict_consensus(
                language=language,
                image_url=str(image_url).strip() if image_url else None,
                image_base64=image_base64 if image_base64 else None,
            )
            if consensus is not None and self._has_medicines(consensus):
                merged = self._intersect_results(primary=result, secondary=consensus)
                if self._has_medicines(merged):
                    result = merged

            verified = await self._verify_medicines_against_image(
                language=language,
                image_url=str(image_url).strip() if image_url else None,
                image_base64=image_base64 if image_base64 else None,
                candidate=result,
            )
            if verified is not None:
                return verified
        return result

    @staticmethod
    def _should_retry_with_data_url(parsed: dict[str, Any]) -> bool:
        meds = parsed.get("medicines", [])
        n_med = len(meds) if isinstance(meds, list) else 0
        status = str(parsed.get("status", "")).strip().lower()
        return status == "failed" or n_med == 0

    @staticmethod
    def _has_medicines(parsed: dict[str, Any]) -> bool:
        meds = parsed.get("medicines", [])
        return isinstance(meds, list) and len(meds) > 0

    async def _build_data_url_from_image_url(self, image_url: str) -> str | None:
        timeout = httpx.Timeout(connect=20.0, read=45.0, write=20.0, pool=20.0)
        try:
            async with httpx.AsyncClient(timeout=timeout, follow_redirects=True) as client:
                res = await client.get(image_url)
                res.raise_for_status()
            content_type = (res.headers.get("content-type", "image/jpeg") or "image/jpeg").split(";")[0].strip().lower()
            if content_type not in {"image/jpeg", "image/jpg", "image/png", "image/webp"}:
                return None
            encoded = base64.b64encode(res.content).decode("ascii")
            mime = "image/jpeg" if content_type == "image/jpg" else content_type
            return f"{mime};base64,{encoded}"
        except Exception:
            return None

    async def _verify_medicines_against_image(
        self,
        *,
        language: str,
        image_url: str | None,
        image_base64: str | None,
        candidate: dict[str, Any],
    ) -> dict[str, Any] | None:
        """Second pass: keep only rows clearly visible on the same image."""
        try:
            verify_message = self._build_verification_message(
                language=language,
                image_url=image_url,
                image_base64=image_base64,
                candidate=candidate,
            )
            verified = await self._request_once(request_payload={"message": verify_message})
            if not self._has_medicines(verified):
                return {
                    "status": "failed",
                    "partial": True,
                    "confidence": float(verified.get("confidence", 0.0)),
                    "medicines": [],
                }
            return verified
        except Exception:
            return None

    async def _extract_strict_consensus(
        self,
        *,
        language: str,
        image_url: str | None,
        image_base64: str | None,
    ) -> dict[str, Any] | None:
        """Independent second extraction to reduce hallucinations via intersection."""
        try:
            msg = self._build_consensus_extraction_message(
                language=language,
                image_url=image_url,
                image_base64=image_base64,
            )
            return await self._request_once(request_payload={"message": msg})
        except Exception:
            return None

    @staticmethod
    def _name_key(name: str) -> str:
        return re.sub(r"[^a-z0-9]+", "", (name or "").lower())

    @staticmethod
    def _pattern_key(pattern: str) -> str:
        return re.sub(r"\s+", "", (pattern or "").lower())

    def _intersect_results(self, *, primary: dict[str, Any], secondary: dict[str, Any]) -> dict[str, Any]:
        p_rows = primary.get("medicines", []) or []
        s_rows = secondary.get("medicines", []) or []
        if not isinstance(p_rows, list) or not isinstance(s_rows, list):
            return primary

        kept: list[dict[str, Any]] = []
        sec_pairs = []
        for s in s_rows:
            if not isinstance(s, dict):
                continue
            sec_pairs.append((self._name_key(str(s.get("name", ""))), self._pattern_key(str(s.get("dosage_pattern", "")))))

        for p in p_rows:
            if not isinstance(p, dict):
                continue
            pn = self._name_key(str(p.get("name", "")))
            pp = self._pattern_key(str(p.get("dosage_pattern", "")))
            matched = False
            for sn, sp in sec_pairs:
                name_match = pn and sn and (pn in sn or sn in pn)
                pattern_match = pp and sp and (pp == sp)
                if name_match and pattern_match:
                    matched = True
                    break
            if matched:
                kept.append(p)

        if not kept:
            return {
                "status": "failed",
                "partial": True,
                "confidence": min(float(primary.get("confidence", 0.0)), float(secondary.get("confidence", 0.0))),
                "medicines": [],
            }

        return {
            "status": "ok",
            "partial": bool(primary.get("partial", False) or secondary.get("partial", False)),
            "confidence": min(float(primary.get("confidence", 0.0)), float(secondary.get("confidence", 0.0))),
            "medicines": kept,
        }

    async def _request_once(
        self,
        *,
        request_payload: dict[str, Any],
    ) -> dict[str, Any]:
        headers = {
            "Authorization": f"Bearer {self.settings.v0_api_key}",
            "Content-Type": "application/json",
        }
        base = self.settings.v0_api_base_url.rstrip("/")
        url = f"{base}{_V0_CHATS_PATH}"
        read_timeout = float(self.settings.v0_timeout_seconds)
        timeout = httpx.Timeout(connect=30.0, read=read_timeout, write=120.0, pool=30.0)
        last_error: Exception | None = None
        t0 = time.perf_counter()

        try:
            async with httpx.AsyncClient(timeout=timeout) as client:
                response = await client.post(url, headers=headers, json=request_payload)
                response.raise_for_status()
            try:
                data = response.json()
            except ValueError as exc:
                raw = response.text[:_LOG_TEXT_PREVIEW] if response.text else ""
                logger.error(
                    "v0.response_not_json reason=body_not_valid_json content_type=%s preview=%s",
                    response.headers.get("content-type", ""),
                    raw,
                )
                raise RetryableAgentError("v0 response body was not valid JSON") from exc
            return self._parse_v0_chats_response(data, duration_ms=(time.perf_counter() - t0) * 1000.0)
        except httpx.TimeoutException:
            ms = (time.perf_counter() - t0) * 1000.0
            logger.error(
                "v0.failed reason=timeout phase=http duration_ms=%.0f read_timeout_seconds=%s",
                ms,
                read_timeout,
            )
            last_error = RetryableAgentError("LLM timeout")
        except httpx.RemoteProtocolError as exc:
            ms = (time.perf_counter() - t0) * 1000.0
            logger.error("v0.failed reason=remote_disconnect phase=http duration_ms=%.0f detail=%s", ms, str(exc))
            last_error = RetryableAgentError(f"v0 connection dropped: {exc}")
        except httpx.HTTPStatusError as exc:
            status_code = exc.response.status_code
            err_body = exc.response.text or ""
            err_json = _safe_error_summary(err_body)
            ms = (time.perf_counter() - t0) * 1000.0
            if status_code == 402:
                logger.error(
                    "v0.failed reason=payment_required phase=http status=402 duration_ms=%.0f error_summary=%s",
                    ms,
                    err_json,
                )
                raise V0PaymentRequiredError(f"v0 API payment required: {err_json}") from exc
            last_error = exc
            logger.error(
                "v0.failed reason=http_error phase=http status=%s duration_ms=%.0f body_preview=%s error_summary=%s",
                status_code,
                ms,
                err_body[:_LOG_TEXT_PREVIEW],
                err_json,
            )
        except httpx.HTTPError as exc:
            ms = (time.perf_counter() - t0) * 1000.0
            logger.error("v0.failed reason=http_transport phase=http duration_ms=%.0f detail=%s", ms, str(exc))
            last_error = exc
        except RetryableAgentError:
            raise
        except Exception as exc:
            ms = (time.perf_counter() - t0) * 1000.0
            logger.error("v0.failed reason=unexpected phase=unknown duration_ms=%.0f", ms, exc_info=exc)
            raise

        logger.error("v0.failed reason=aborted_raising last_error_type=%s", type(last_error).__name__)
        raise RetryableAgentError("v0 request failed") from last_error

    def _parse_v0_chats_response(self, data: dict[str, Any], *, duration_ms: float) -> dict[str, Any]:
        top_keys = list(data.keys()) if isinstance(data, dict) else []
        messages = data.get("messages", [])
        if not messages:
            logger.error(
                "v0.parse reason=no_message_list duration_ms=%.0f top_level_keys=%s",
                duration_ms,
                top_keys,
            )
            raise RetryableAgentError("Empty response from v0")
        role_counts: dict[str, int] = {}
        for m in messages:
            if isinstance(m, dict):
                r = str(m.get("role", "?"))
                role_counts[r] = role_counts.get(r, 0) + 1
        text_response = ""
        for message in reversed(messages):
            if message.get("role") == "assistant":
                text_response = _content_to_text(message.get("content"))
                if text_response:
                    break
        if not text_response:
            logger.error(
                "v0.parse reason=empty_assistant_text duration_ms=%.0f role_counts=%s (need assistant with content)",
                duration_ms,
                role_counts,
            )
            raise RetryableAgentError("Empty assistant content from v0")
        try:
            parsed = extract_json_object(text_response)
        except Exception as exc:
            logger.error(
                "v0.parse reason=invalid_json_in_assistant exc=%s text_len=%s preview=%s",
                type(exc).__name__,
                len(text_response),
                text_response[:_LOG_TEXT_PREVIEW],
            )
            raise RetryableAgentError("Invalid JSON output from v0") from exc
        normalized = self._normalize_extraction_response(parsed)
        return normalized

    @staticmethod
    def _build_extraction_message(
        language: str,
        *,
        image_url: str | None,
        image_base64: str | None,
    ) -> str:
        system = (
            "You are a clinical OCR sub-system. Your response must be parsed by strict JSON only.\n\n"
            "Output rules (critical):\n"
            "- Return exactly one JSON object, and nothing else.\n"
            "- Do not use markdown, code fences, or ```json.\n"
            "- Do not explain your reasoning, do not build apps or pages, and do not describe a UI.\n"
            "- Do not add any text before the opening { or after the closing }.\n"
        )
        user = (
            "Read ONLY what is visible in the prescription image (provided at the end of this message). "
            "Return one JSON object with keys: 'status' (string: 'ok' or 'failed'), 'partial' (boolean), "
            "'confidence' (number 0-1), 'medicines' (array).\n\n"
            "Before extracting, do a strict visual transcription of the medicine lines mentally and only output rows that "
            "are explicitly present in those visible lines.\n\n"
            "For EACH medicine object, include ALL of:\n"
            "- 'name': string — copy the visible wording from the image exactly as written (including imperfect spellings "
            "or handwriting ambiguity). DO NOT replace with a guessed standard drug name.\n"
            "- 'name_legible': boolean — true only if every letter of the name is clearly readable from the image.\n"
            "- 'dosage_pattern': string — dose and frequency text as on the label (e.g. '500mg tds', '150mg bd').\n"
            "- 'duration_days': integer.\n"
            "- 'instructions': string or null — short patient-facing line from the script if visible.\n"
            "- 'confidence': number 0-1 for this row.\n"
            "- 'reminder_times_24h': array of strings — each 'HH:MM' in 24-hour format (e.g. '09:00', '14:00'). "
            "Length MUST match daily dose count implied by the regimen (e.g. twice daily → exactly 2 times; "
            "three times daily → exactly 3). Space times across typical waking hours (roughly 08:00–21:00). "
            "These are default push-notification times the app will offer; they must be consistent with dosage_pattern.\n\n"
            "STRICT rules:\n"
            "1) Never invent a medicine that does not appear on this image.\n"
            "2) Never use prior medical knowledge to substitute a different medicine name.\n"
            "3) If a row is uncertain, keep only what is visibly readable and lower confidence/name_legible.\n"
            "4) Prefer best-effort partial extraction: if any medicine-like row is visible, return it with lower confidence "
            "and partial=true instead of medicines=[].\n"
            "5) Use status='failed' with medicines=[] only when absolutely nothing readable exists in the image.\n"
            "6) Prefer fewer high-confidence rows over guessing names.\n\n"
            f"Prescriber / patient language hint for free-text fields: {language}."
        )
        if image_url:
            tail = f"Prescription image URL: {image_url}"
        else:
            assert image_base64 is not None
            if ";base64," in image_base64:
                tail = f"Prescription image data URL: data:{image_base64}"
            else:
                tail = f"Prescription image data URL: data:image/jpeg;base64,{image_base64}"
        return f"{system}\n\n{user}\n\n{tail}"

    @staticmethod
    def _build_verification_message(
        language: str,
        *,
        image_url: str | None,
        image_base64: str | None,
        candidate: dict[str, Any],
    ) -> str:
        candidate_json = json.dumps(candidate, ensure_ascii=False)
        system = (
            "You are a strict medical OCR verifier. Return strict JSON only."
        )
        user = (
            "You are given a prescription image and a candidate extraction JSON.\n"
            "Verify each medicine row against the visible image text.\n"
            "KEEP a row only if the medicine name and dosage/frequency are explicitly visible.\n"
            "DROP any guessed/hallucinated row.\n"
            "For kept rows, you may correct fields to match visible text exactly.\n\n"
            "Return exactly one JSON object with keys: status, partial, confidence, medicines.\n"
            "Use status='failed' and medicines=[] if no candidate rows are clearly supported by the image.\n"
            "Never add medicines that are not in the candidate list.\n"
            f"Language hint: {language}.\n\n"
            f"Candidate extraction JSON:\n{candidate_json}"
        )
        if image_url:
            tail = f"Prescription image URL: {image_url}"
        else:
            assert image_base64 is not None
            if ";base64," in image_base64:
                tail = f"Prescription image data URL: data:{image_base64}"
            else:
                tail = f"Prescription image data URL: data:image/jpeg;base64,{image_base64}"
        return f"{system}\n\n{user}\n\n{tail}"

    @staticmethod
    def _build_consensus_extraction_message(
        language: str,
        *,
        image_url: str | None,
        image_base64: str | None,
    ) -> str:
        system = "You are a strict handwriting OCR extractor for prescriptions. Return strict JSON only."
        user = (
            "Extract ONLY medicine rows that are explicitly visible in the Rx medicine list.\n"
            "Do not infer diagnosis plans, common regimens, or likely medicines.\n"
            "Do not correct medicine names to standardized brands/generics.\n"
            "Copy visible text as-is.\n\n"
            "Return exactly one JSON object with: status, partial, confidence, medicines.\n"
            "Each medicine: name, name_legible, dosage_pattern, duration_days, instructions, confidence, reminder_times_24h.\n"
            "If uncertain, return fewer rows with lower confidence.\n"
            "If no row is clearly readable, return status='failed' and medicines=[].\n"
            f"Language hint: {language}."
        )
        if image_url:
            tail = f"Prescription image URL: {image_url}"
        else:
            assert image_base64 is not None
            if ";base64," in image_base64:
                tail = f"Prescription image data URL: data:{image_base64}"
            else:
                tail = f"Prescription image data URL: data:image/jpeg;base64,{image_base64}"
        return f"{system}\n\n{user}\n\n{tail}"

    @staticmethod
    def _normalize_extraction_response(payload: dict[str, Any]) -> dict[str, Any]:
        """Normalize provider response to internal extraction contract."""
        raw_status = str(payload.get("status", "")).strip().lower()
        if raw_status in {"ok", "success", "completed"}:
            status = "ok"
        elif raw_status in {"failed", "error", "invalid"}:
            status = "failed"
        else:
            status = "ok" if payload.get("medicines") else "failed"

        medicines = payload.get("medicines", [])
        if not isinstance(medicines, list):
            medicines = []

        partial = bool(payload.get("partial", False))
        confidence_value = payload.get("confidence", 0.0)
        try:
            confidence = float(confidence_value)
        except (TypeError, ValueError):
            confidence = 0.0

        return {
            "status": status,
            "partial": partial,
            "confidence": max(0.0, min(confidence, 1.0)),
            "medicines": medicines,
        }
