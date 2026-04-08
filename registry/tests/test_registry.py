"""Registry service tests.

Covers:
- Upload a dummy .safetensors file
- Full happy-path: upload → session_token → /assets/access → presigned URL → download
- Single-use: presigned URL cannot be redeemed a second time
- Expired session_token is rejected at /assets/access
- Asset IDs that don't match the session token are rejected
- /assets/verify rejects unknown or mismatched asset IDs
"""

import os
import time
import uuid

import pytest
from httpx import AsyncClient

from app.jwt_utils import encode as jwt_encode

SECRET_KEY = os.getenv("SHIELD_JWT_SECRET", "dev-secret")
RIGHTS_HOLDER_ID = "test-rights-holder"

# 1 KB of zeroed bytes standing in for a real .safetensors file
DUMMY_SAFETENSORS = bytes(1024)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_session_token(request_id: str, asset_ids: list[str], expires_in: int = 300) -> str:
    return jwt_encode(
        {
            "request_id": request_id,
            "asset_ids": asset_ids,
            "exp": int(time.time()) + expires_in,
        },
        SECRET_KEY,
    )


async def _upload(client: AsyncClient, rights_holder_id: str = RIGHTS_HOLDER_ID) -> str:
    """Upload the dummy file and return asset_id."""
    resp = await client.post(
        "/assets/upload",
        data={"rights_holder_id": rights_holder_id},
        files={
            "file": ("test_lora.safetensors", DUMMY_SAFETENSORS, "application/octet-stream")
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["asset_id"]


def _token_from_url(presigned_url: str) -> str:
    """Extract the download token UUID from a presigned URL path."""
    return presigned_url.rstrip("/").split("/")[-1]


# ---------------------------------------------------------------------------
# Upload
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_upload_returns_asset_id(client: AsyncClient):
    asset_id = await _upload(client)
    # Must be a valid UUID string
    uuid.UUID(asset_id)


# ---------------------------------------------------------------------------
# Happy-path: upload → get presigned URL → download
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_full_happy_path(client: AsyncClient):
    asset_id = await _upload(client)
    request_id = str(uuid.uuid4())
    session_token = _make_session_token(request_id, [asset_id])

    # 1. Exchange session_token for presigned URLs
    resp = await client.post(
        "/assets/access",
        json={"session_token": session_token, "asset_ids": [asset_id]},
    )
    assert resp.status_code == 200, resp.text
    urls = resp.json()["urls"]
    assert asset_id in urls

    # 2. Download the file via the presigned URL
    presigned_url = urls[asset_id]
    token_id = _token_from_url(presigned_url)

    resp = await client.get(f"/assets/download/{token_id}")
    assert resp.status_code == 200
    assert resp.content == DUMMY_SAFETENSORS


# ---------------------------------------------------------------------------
# Single-use: second redemption of same presigned URL must fail
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_presigned_url_is_single_use(client: AsyncClient):
    asset_id = await _upload(client)
    session_token = _make_session_token(str(uuid.uuid4()), [asset_id])

    resp = await client.post(
        "/assets/access",
        json={"session_token": session_token, "asset_ids": [asset_id]},
    )
    assert resp.status_code == 200, resp.text
    token_id = _token_from_url(resp.json()["urls"][asset_id])

    # First download — must succeed
    resp1 = await client.get(f"/assets/download/{token_id}")
    assert resp1.status_code == 200

    # Second download — must be rejected (410 Gone)
    resp2 = await client.get(f"/assets/download/{token_id}")
    assert resp2.status_code == 410


# ---------------------------------------------------------------------------
# Expired session_token is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_expired_session_token_rejected(client: AsyncClient):
    asset_id = await _upload(client)
    # Token that expired 10 seconds ago
    expired_token = _make_session_token(str(uuid.uuid4()), [asset_id], expires_in=-10)

    resp = await client.post(
        "/assets/access",
        json={"session_token": expired_token, "asset_ids": [asset_id]},
    )
    assert resp.status_code == 401


# ---------------------------------------------------------------------------
# asset_ids mismatch between request and token is rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_asset_ids_mismatch_rejected(client: AsyncClient):
    asset_id = await _upload(client)
    other_id = str(uuid.uuid4())

    # Token encodes [asset_id] but request asks for [other_id]
    session_token = _make_session_token(str(uuid.uuid4()), [asset_id])

    resp = await client.post(
        "/assets/access",
        json={"session_token": session_token, "asset_ids": [other_id]},
    )
    assert resp.status_code == 403


# ---------------------------------------------------------------------------
# /assets/verify endpoint
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_verify_valid_assets(client: AsyncClient):
    asset_id = await _upload(client)

    resp = await client.post(
        "/assets/verify",
        json={"asset_ids": [asset_id], "rights_holder_id": RIGHTS_HOLDER_ID},
    )
    assert resp.status_code == 200
    assert resp.json()["valid"] is True


@pytest.mark.asyncio
async def test_verify_unknown_asset_rejected(client: AsyncClient):
    unknown_id = str(uuid.uuid4())

    resp = await client.post(
        "/assets/verify",
        json={"asset_ids": [unknown_id], "rights_holder_id": RIGHTS_HOLDER_ID},
    )
    assert resp.status_code == 400


@pytest.mark.asyncio
async def test_verify_wrong_rights_holder_rejected(client: AsyncClient):
    asset_id = await _upload(client, rights_holder_id="owner-a")

    resp = await client.post(
        "/assets/verify",
        json={"asset_ids": [asset_id], "rights_holder_id": "owner-b"},
    )
    assert resp.status_code == 400
