"""Cloudinary image upload service."""

from __future__ import annotations

import asyncio
from io import BytesIO
from typing import Any

import cloudinary
import cloudinary.uploader

from app.core.config import get_settings

_ALLOWED_TYPES = frozenset({"image/jpeg", "image/png", "image/webp"})


class CloudinaryService:
    """Upload prescription images to Cloudinary (blocking SDK wrapped in thread)."""

    def __init__(self) -> None:
        self.settings = get_settings()
        cloudinary.config(
            cloud_name=self.settings.cloudinary_cloud_name,
            api_key=self.settings.cloudinary_api_key,
            api_secret=self.settings.cloudinary_api_secret,
            secure=True,
        )

    def validate_content_type(self, content_type: str | None) -> str:
        """Return normalized content type or raise ValueError."""
        if not content_type:
            raise ValueError("Image content type is required")
        normalized = content_type.split(";")[0].strip().lower()
        if normalized not in _ALLOWED_TYPES:
            raise ValueError(f"Unsupported image type: {content_type}. Use JPEG, PNG, or WebP.")
        return normalized

    async def upload_prescription_image(self, file_bytes: bytes, filename: str) -> dict[str, Any]:
        """Upload image bytes to Cloudinary and return URL metadata."""
        if len(file_bytes) > self.settings.max_prescription_upload_bytes:
            raise ValueError(f"Image exceeds maximum size of {self.settings.max_prescription_upload_bytes} bytes")

        folder = self.settings.cloudinary_folder.strip().strip("/")

        def _upload() -> dict[str, Any]:
            return cloudinary.uploader.upload(
                BytesIO(file_bytes),
                folder=folder or None,
                resource_type="image",
                use_filename=False,
                unique_filename=True,
                overwrite=False,
            )

        result = await asyncio.to_thread(_upload)
        secure_url = result.get("secure_url")
        public_id = result.get("public_id")
        if not secure_url or not public_id:
            raise RuntimeError("Cloudinary upload did not return secure_url/public_id")
        return {"secure_url": secure_url, "public_id": public_id, "bytes": len(file_bytes)}

    async def delete_prescription_image(self, public_id: str) -> None:
        """Delete uploaded image from Cloudinary (best-effort)."""
        if not public_id:
            return

        def _destroy() -> dict[str, Any]:
            return cloudinary.uploader.destroy(public_id, resource_type="image", invalidate=True)

        await asyncio.to_thread(_destroy)
