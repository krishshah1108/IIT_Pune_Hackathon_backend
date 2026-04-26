"""Normalization and parsing helpers."""

import base64
import hashlib
import re

DOSAGE_ALIASES = {
    "bd": "1-0-1",
    "tds": "1-1-1",
    "od": "1-0-0",
    "hs": "0-0-1",
}


def normalize_medicine_name(name: str) -> str:
    """Normalize medicine name for dedupe/index search."""
    return re.sub(r"[^a-z0-9]+", " ", name.lower()).strip()


def normalize_dosage_pattern(pattern: str) -> str:
    """Convert shorthand dosage to canonical format."""
    cleaned = pattern.strip().lower()
    return DOSAGE_ALIASES.get(cleaned, cleaned)


def parse_frequency(pattern: str) -> int:
    """Estimate daily frequency from dosage pattern."""
    pattern = normalize_dosage_pattern(pattern)
    if re.fullmatch(r"\d-\d-\d", pattern):
        return sum(int(part) for part in pattern.split("-"))
    return 1


def safe_image_hash(image_base64: str) -> str:
    """Hash raw image payload to detect duplicate uploads."""
    try:
        raw = base64.b64decode(image_base64, validate=False)
    except Exception:
        raw = image_base64.encode("utf-8")
    return hashlib.sha256(raw).hexdigest()


def hash_bytes(data: bytes) -> str:
    """SHA-256 hash of raw bytes for deduplication."""
    return hashlib.sha256(data).hexdigest()
