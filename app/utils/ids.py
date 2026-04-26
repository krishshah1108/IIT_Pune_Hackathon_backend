"""Identifier helpers."""

from uuid import uuid4


def new_id(prefix: str) -> str:
    """Create prefixed identifier."""
    return f"{prefix}_{uuid4().hex}"
