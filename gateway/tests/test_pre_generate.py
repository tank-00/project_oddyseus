"""Tests for POST /v1/pre-generate covering all three policy decision paths.

The policy service HTTP call is mocked via unittest.mock so these tests run
without a live policy service.  Auth uses the same test credentials seeded in
conftest.py (client_id=test-tool, client_secret=test-secret).
"""

import pytest
from unittest.mock import AsyncMock, patch
from httpx import AsyncClient


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _policy_resp(decision: str, matched_rule: str, reason: str) -> dict:
    return {
        "decision": decision,
        "matched_rule": matched_rule,
        "reason": reason,
        "request_id": "00000000-0000-0000-0000-000000000001",
    }


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


BASE_BODY = {
    "rights_holder_id": "test-rights-holder",
    "prompt": "Draw a portrait of a famous musician",
    "content_categories": ["art"],
    "asset_ids": ["asset-1", "asset-2"],
}


# ---------------------------------------------------------------------------
# Decision path: approve (fan use)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pre_generate_fan_use_returns_session_token(client: AsyncClient):
    token = await _get_bearer_token(client)

    with patch(
        "app.pre_generate._call_policy_service",
        new_callable=AsyncMock,
        return_value=_policy_resp("approve", "use_type", "Use type 'fan' maps to 'approve'"),
    ):
        resp = await client.post(
            "/v1/pre-generate",
            headers={"Authorization": f"Bearer {token}"},
            json={**BASE_BODY, "use_type": "fan"},
        )

    assert resp.status_code == 200
    body = resp.json()
    assert body["decision"] == "approve"
    assert "session_token" in body
    assert "reason" in body
    assert "request_id" in body
    assert body["reason"] == "Use type 'fan' maps to 'approve'"


# ---------------------------------------------------------------------------
# Decision path: reject (advertising use)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pre_generate_advertising_use_returns_403(client: AsyncClient):
    token = await _get_bearer_token(client)

    with patch(
        "app.pre_generate._call_policy_service",
        new_callable=AsyncMock,
        return_value=_policy_resp("reject", "use_type", "Use type 'advertising' maps to 'reject'"),
    ):
        resp = await client.post(
            "/v1/pre-generate",
            headers={"Authorization": f"Bearer {token}"},
            json={**BASE_BODY, "use_type": "advertising"},
        )

    assert resp.status_code == 403
    assert "advertising" in resp.json()["detail"]


# ---------------------------------------------------------------------------
# Decision path: escalate (commercial use)
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pre_generate_commercial_use_returns_202(client: AsyncClient):
    token = await _get_bearer_token(client)

    with patch(
        "app.pre_generate._call_policy_service",
        new_callable=AsyncMock,
        return_value=_policy_resp(
            "escalate", "use_type", "Use type 'commercial' maps to 'escalate'"
        ),
    ):
        resp = await client.post(
            "/v1/pre-generate",
            headers={"Authorization": f"Bearer {token}"},
            json={**BASE_BODY, "use_type": "commercial"},
        )

    assert resp.status_code == 202
    body = resp.json()
    assert "detail" in body
    assert "commercial" in body["detail"]


# ---------------------------------------------------------------------------
# Auth guard: unauthenticated request should be rejected
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_pre_generate_requires_auth(client: AsyncClient):
    resp = await client.post(
        "/v1/pre-generate",
        json={**BASE_BODY, "use_type": "fan"},
    )
    assert resp.status_code in (401, 403)
