"""Shield SDK — Python client for the Shield gateway API."""

from .client import ShieldClient
from .exceptions import ShieldAPIError, ShieldAuthError, ShieldEscalateError, ShieldRejectedError
from .models import AssetURL, DetectResult, PostGenerateResult, PreGenerateResult

__all__ = [
    "ShieldClient",
    "ShieldRejectedError",
    "ShieldEscalateError",
    "ShieldAuthError",
    "ShieldAPIError",
    "PreGenerateResult",
    "AssetURL",
    "PostGenerateResult",
    "DetectResult",
]
