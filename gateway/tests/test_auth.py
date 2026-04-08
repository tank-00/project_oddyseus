import pytest
import pytest_asyncio
from httpx import AsyncClient


@pytest.mark.asyncio
async def test_token_issued_with_valid_credentials(client: AsyncClient):
    response = await client.post(
        "/auth/token",
        data={
            "client_id": "test-tool",
            "client_secret": "test-secret",
            "end_user_id": "test-user",
        },
    )
    assert response.status_code == 200
    body = response.json()
    assert "access_token" in body
    assert body["token_type"] == "bearer"
    assert body["expires_in"] == 3600


@pytest.mark.asyncio
async def test_token_rejected_with_wrong_secret(client: AsyncClient):
    response = await client.post(
        "/auth/token",
        data={
            "client_id": "test-tool",
            "client_secret": "wrong-secret",
            "end_user_id": "test-user",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_token_rejected_with_unknown_client(client: AsyncClient):
    response = await client.post(
        "/auth/token",
        data={
            "client_id": "no-such-client",
            "client_secret": "test-secret",
            "end_user_id": "test-user",
        },
    )
    assert response.status_code == 401


@pytest.mark.asyncio
async def test_require_auth_passes_with_valid_token(client: AsyncClient):
    # First obtain a token
    token_response = await client.post(
        "/auth/token",
        data={
            "client_id": "test-tool",
            "client_secret": "test-secret",
            "end_user_id": "test-user",
        },
    )
    assert token_response.status_code == 200
    token = token_response.json()["access_token"]

    # Hit the protected route
    response = await client.get(
        "/protected",
        headers={"Authorization": f"Bearer {token}"},
    )
    assert response.status_code == 200
    claims = response.json()
    assert claims["client_id"] == "test-tool"
    assert claims["tool_provider_id"] == "test-tool"
    assert claims["client_app_id"] == "test-app"
    assert claims["end_user_id"] == "test-user"


@pytest.mark.asyncio
async def test_require_auth_fails_without_token(client: AsyncClient):
    response = await client.get("/protected")
    # HTTPBearer raises 401 (no credentials) or 403 (bad scheme) depending on version
    assert response.status_code in (401, 403)


@pytest.mark.asyncio
async def test_require_auth_fails_with_invalid_token(client: AsyncClient):
    response = await client.get(
        "/protected",
        headers={"Authorization": "Bearer this.is.not.a.valid.token"},
    )
    assert response.status_code == 401
