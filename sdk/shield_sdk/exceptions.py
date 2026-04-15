"""Shield SDK exceptions."""

from __future__ import annotations


class ShieldError(Exception):
    """Base exception for all Shield SDK errors."""

    def __init__(self, message: str, reason: str | None = None):
        super().__init__(message)
        self.reason = reason


class ShieldRejectedError(ShieldError):
    """Raised when the policy engine returns *reject*."""


class ShieldEscalateError(ShieldError):
    """Raised when the policy engine returns *escalate* (human review needed)."""


class ShieldAuthError(ShieldError):
    """Raised when token acquisition or refresh fails."""


class ShieldAPIError(ShieldError):
    """Raised for unexpected HTTP errors from the gateway."""

    def __init__(self, message: str, status_code: int | None = None):
        super().__init__(message)
        self.status_code = status_code
