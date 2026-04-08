"""POST /v1/get-assets — proxy to the registry for presigned asset download URLs.

Protected by require_auth().  Forwards the caller's session_token and asset_ids
to the registry /assets/access endpoint and returns the presigned URLs.
"""
import os

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel

from .auth import require_auth
from .models import IdentityClaims

REGISTRY_SERVICE_URL = os.getenv("REGISTRY_SERVICE_URL", "http://registry:8002")

router = APIRouter(prefix="/v1", tags=["generation"])


class GetAssetsRequest(BaseModel):
    session_token: str
    asset_ids: list[str]


async def _call_registry_access(payload: dict) -> dict:
    """Forward request to the registry /assets/access endpoint."""
    async with httpx.AsyncClient() as http:
        resp = await http.post(f"{REGISTRY_SERVICE_URL}/assets/access", json=payload)
        resp.raise_for_status()
        return resp.json()


@router.post("/get-assets")
async def get_assets(
    body: GetAssetsRequest,
    claims: IdentityClaims = Depends(require_auth),  # noqa: ARG001 — enforces auth
):
    """Return presigned download URLs for the approved assets."""
    try:
        result = await _call_registry_access(
            {
                "session_token": body.session_token,
                "asset_ids": body.asset_ids,
            }
        )
    except httpx.HTTPStatusError as exc:
        detail = "Registry error"
        try:
            detail = exc.response.json().get("detail", detail)
        except Exception:
            pass
        raise HTTPException(status_code=exc.response.status_code, detail=detail)
    except httpx.RequestError:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Registry service unavailable",
        )

    return result
