"""POST /assets/upload — gateway proxy to the registry upload endpoint.

Accepts multipart/form-data (file + rights_holder_id) and forwards the
request to the registry service, returning the resulting asset_id.
"""
import os

import httpx
from fastapi import APIRouter, Form, HTTPException, UploadFile, status

REGISTRY_SERVICE_URL = os.getenv("REGISTRY_SERVICE_URL", "http://registry:8002")

router = APIRouter(tags=["assets"])


@router.post("/assets/upload")
async def upload_asset(
    file: UploadFile,
    rights_holder_id: str = Form(...),
):
    """Proxy a file upload to the registry service and return the asset_id."""
    file_bytes = await file.read()

    try:
        async with httpx.AsyncClient() as http:
            resp = await http.post(
                f"{REGISTRY_SERVICE_URL}/assets/upload",
                data={"rights_holder_id": rights_holder_id},
                files={"file": (file.filename, file_bytes, file.content_type)},
            )
            resp.raise_for_status()
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

    return resp.json()
