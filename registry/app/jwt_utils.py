"""Minimal HS256 JWT implementation using stdlib only (hmac + hashlib).

Identical to the gateway's jwt_utils — kept local to avoid cross-service imports.
"""
import base64
import hashlib
import hmac
import json
import time
from typing import Any


def _b64url_encode(data: bytes) -> str:
    return base64.urlsafe_b64encode(data).rstrip(b"=").decode()


def _b64url_decode(s: str) -> bytes:
    padding = 4 - len(s) % 4
    if padding != 4:
        s += "=" * padding
    return base64.urlsafe_b64decode(s)


def encode(payload: dict[str, Any], secret: str, algorithm: str = "HS256") -> str:
    if algorithm != "HS256":
        raise ValueError(f"Unsupported algorithm: {algorithm}")

    header = _b64url_encode(json.dumps({"alg": "HS256", "typ": "JWT"}, separators=(",", ":")).encode())
    body = _b64url_encode(json.dumps(payload, separators=(",", ":")).encode())
    signing_input = f"{header}.{body}"
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return f"{signing_input}.{_b64url_encode(sig)}"


class ExpiredSignatureError(Exception):
    pass


class InvalidTokenError(Exception):
    pass


def decode(token: str, secret: str, algorithms: list[str] | None = None) -> dict[str, Any]:
    try:
        header_b64, payload_b64, sig_b64 = token.split(".")
    except ValueError:
        raise InvalidTokenError("Malformed token")

    try:
        header = json.loads(_b64url_decode(header_b64))
    except Exception:
        raise InvalidTokenError("Malformed header")

    alg = header.get("alg", "")
    if algorithms and alg not in algorithms:
        raise InvalidTokenError(f"Algorithm {alg!r} not allowed")

    signing_input = f"{header_b64}.{payload_b64}"
    expected_sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    try:
        actual_sig = _b64url_decode(sig_b64)
    except Exception:
        raise InvalidTokenError("Malformed signature")

    if not hmac.compare_digest(expected_sig, actual_sig):
        raise InvalidTokenError("Signature verification failed")

    try:
        payload = json.loads(_b64url_decode(payload_b64))
    except Exception:
        raise InvalidTokenError("Malformed payload")

    exp = payload.get("exp")
    if exp is not None and time.time() > exp:
        raise ExpiredSignatureError("Token has expired")

    return payload
