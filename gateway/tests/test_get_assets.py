"""Tests for POST /v1/get-assets.

The registry /assets/access call is mocked so these tests run without a live
registry.  Auth uses the same test credentials seeded in conftest.py.
"""
import time
import uuid
from unittest.mock import AsyncMock, patch

import pytest
from httpx import AsyncClient, HTTPStatusError, Response

from app.jwt_utils import encode as jwt_encode

SECRET_KEY = "dev-secret"


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _get_bearer_token(client: AsyncClient) -> str:
    resp = await client.post(
        "/auth/token",
        data={
            "client_id": "test-tool",
            "client_secret": "test-secret",
            "end_user_id": "test-user",
        },
    )
    assert resp.status_code == 200, resp.text
    return resp.json()["access_token"]


def _make_session_token(asset_ids: list[str], expires_in: int = 300) -> str:
    return jwt_encode(
        {
            "request_id": str(uuid.uuid4()),
            "asset_ids": asset_ids,
            "exp": int(time.time()) + expires_in,
        },
        SECRET_KEY,
    )


ASSET_ID = str(uuid.uuid4())
PRESIGNED_URL = f"http://registry:8002/assets/download/{uuid.uuid4()}"


# ---------------------------------------------------------------------------
# Happy path: proxies to registry and returns presigned URLs
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_assets_returns_presigned_urls(client: AsyncClient):
    token = await _get_bearer_token(client)
    session_token = _make_session_token([ASSET_ID])

    registry_response = {"urls": {ASSET_ID: PRESIGNED_URL}}

    with patch(
        "app.get_assets._call_registry_access",
        new_callable=AsyncMock,
        return_value=registry_response,
    ):
        resp = await client.post(
            "/v1/get-assets",
            headers={"Authorization": f"Bearer {token}"},
            json={"session_token": session_token, "asset_ids": [ASSET_ID]},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert "urls" in body
    assert body["urls"][ASSET_ID] == PRESIGNED_URL


# ---------------------------------------------------------------------------
# Auth guard: unauthenticated request must be rejected
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_assets_requires_auth(client: AsyncClient):
    session_token = _make_session_token([ASSET_ID])

    resp = await client.post(
        "/v1/get-assets",
        json={"session_token": session_token, "asset_ids": [ASSET_ID]},
    )
    assert resp.status_code in (401, 403)


# ---------------------------------------------------------------------------
# Registry returns an error — gateway propagates the status code
# ---------------------------------------------------------------------------


@pytest.mark.asyncio
async def test_get_assets_propagates_registry_error(client: AsyncClient):
    token = await _get_bearer_token(client)
    session_token = _make_session_token([ASSET_ID])

    mock_response = Response(status_code=401, json={"detail": "Session token has expired"})

    async def _raise(*_args, **_kwargs):
        raise HTTPStatusError("expired", request=None, response=mock_response)

    with patch("app.get_assets._call_registry_access", side_effect=_raise):
        resp = await client.post(
            "/v1/get-assets",
            headers={"Authorization": f"Bearer {token}"},
            json={"session_token": session_token, "asset_ids": [ASSET_ID]},
        )

    assert resp.status_code == 401
    assert "expired" in resp.json()["detail"]
