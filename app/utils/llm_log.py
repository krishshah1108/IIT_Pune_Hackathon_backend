"""Helpers to log raw LLM text safely (length-limited, JSON-escaped for log lines)."""

from __future__ import annotations

import json
import logging

__all__ = ["log_model_text"]


def log_model_text(
    log: logging.Logger,
    service_prefix: str,
    text: str,
    max_chars: int,
) -> None:
    """Log assistant/model output. max_chars=0 logs only the character count (no content)."""
    n = len(text)
    if max_chars <= 0:
        log.info(
            "%s llm_text_chars=%s (content omitted: LLM_RESPONSE_LOG_MAX_CHARS=0)",
            service_prefix,
            n,
        )
        return
    cap = min(n, max_chars)
    chunk = text[:cap]
    truncated = cap < n
    try:
        escaped = json.dumps(chunk, ensure_ascii=False)
    except Exception:
        escaped = json.dumps(repr(chunk))
    log.info(
        "%s llm_response full_len=%s log_len=%s truncated=%s text=%s",
        service_prefix,
        n,
        cap,
        truncated,
        escaped,
    )
