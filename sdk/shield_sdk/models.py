"""Shield SDK result types."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime


@dataclass
class PreGenerateResult:
    """Returned by :meth:`ShieldClient.pre_generate` on approval."""

    decision: str
    session_token: str
    reason: str
    asset_ids: list[str]


@dataclass
class AssetURL:
    """A single presigned asset download URL."""

    asset_id: str
    url: str
    expires_at: str | None = None


@dataclass
class PostGenerateResult:
    """Returned by :meth:`ShieldClient.post_generate`."""

    watermarked_image_bytes: bytes
    generation_id: str
    output_hash: str


@dataclass
class DetectResult:
    """Returned by :meth:`ShieldClient.decode_watermark`."""

    found: bool
    generation_id: str | None = None
    transaction_metadata: dict | None = None
