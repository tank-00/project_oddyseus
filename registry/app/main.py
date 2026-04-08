"""Shield Registry service — port 8002 (internal, no auth required).

Endpoints
---------
POST /assets/upload   — store a file, return asset_id
POST /assets/access   — validate session_token JWT, return presigned download URLs
POST /assets/verify   — internal; confirm asset_ids belong to a rights_holder
GET  /assets/download/{token_id} — serve file for local-storage presigned URLs
"""
import os
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, Form, HTTPException, Response, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .jwt_utils import ExpiredSignatureError, InvalidTokenError
from .jwt_utils import decode as jwt_decode
from .models import (
    Asset,
    AssetAccessRequest,
    AssetAccessResponse,
    AssetUploadResponse,
    AssetVerifyRequest,
    UsedToken,
)
from .store import AssetStore, get_store

SECRET_KEY = os.getenv("SHIELD_JWT_SECRET", "dev-secret")
PRESIGN_EXPIRY_SECONDS = 60

app = FastAPI(title="Shield Registry", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "registry"}


# ---------------------------------------------------------------------------
# POST /assets/upload
# ---------------------------------------------------------------------------


@app.post("/assets/upload", response_model=AssetUploadResponse)
async def upload_asset(
    file: UploadFile,
    rights_holder_id: str = Form(...),
    db: AsyncSession = Depends(get_db),
    store: AssetStore = Depends(get_store),
):
    """Store a file and create an assets record. Returns asset_id."""
    file_bytes = await file.read()
    asset_id = uuid.uuid4()
    asset_id_str = str(asset_id)

    await store.put(asset_id_str, file_bytes)

    asset = Asset(
        id=asset_id,
        rights_holder_id=rights_holder_id,
        filename=file.filename or "unknown",
        content_type=file.content_type or "application/octet-stream",
        size_bytes=len(file_bytes),
    )
    db.add(asset)
    await db.commit()

    return AssetUploadResponse(asset_id=asset_id_str)


# ---------------------------------------------------------------------------
# POST /assets/access
# ---------------------------------------------------------------------------


@app.post("/assets/access", response_model=AssetAccessResponse)
async def access_assets(
    body: AssetAccessRequest,
    db: AsyncSession = Depends(get_db),
    store: AssetStore = Depends(get_store),
):
    """Validate a session_token JWT and return one presigned URL per asset."""
    try:
        payload = jwt_decode(body.session_token, SECRET_KEY, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Session token has expired",
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid session token",
        )

    token_asset_ids: list[str] = payload.get("asset_ids", [])

    if set(body.asset_ids) != set(token_asset_ids):
        raise HTTPException(
            status_code=status.HTTP_403_FORBIDDEN,
            detail="Requested asset_ids do not match those encoded in the session token",
        )

    now = datetime.now(timezone.utc)
    expires_at = now + timedelta(seconds=PRESIGN_EXPIRY_SECONDS)
    urls: dict[str, str] = {}

    for asset_id_str in body.asset_ids:
        try:
            asset_uuid = uuid.UUID(asset_id_str)
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid asset_id format: {asset_id_str}",
            )

        result = await db.execute(
            select(Asset).where(Asset.id == asset_uuid, Asset.is_active == True)  # noqa: E712
        )
        asset = result.scalar_one_or_none()
        if not asset:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Asset not found: {asset_id_str}",
            )

        token_id = uuid.uuid4()
        used_token = UsedToken(
            id=token_id,
            asset_id=asset_uuid,
            expires_at=expires_at,
            redeemed=False,
        )
        db.add(used_token)
        urls[asset_id_str] = store.make_download_url(asset_id_str, str(token_id))

    await db.commit()
    return AssetAccessResponse(urls=urls)


# ---------------------------------------------------------------------------
# POST /assets/verify  (called by the gateway before issuing a session_token)
# ---------------------------------------------------------------------------


@app.post("/assets/verify")
async def verify_assets(
    body: AssetVerifyRequest,
    db: AsyncSession = Depends(get_db),
):
    """Confirm every asset_id exists, is active, and belongs to rights_holder_id."""
    invalid_ids: list[str] = []

    for asset_id_str in body.asset_ids:
        try:
            asset_uuid = uuid.UUID(asset_id_str)
        except ValueError:
            invalid_ids.append(asset_id_str)
            continue

        result = await db.execute(
            select(Asset).where(
                Asset.id == asset_uuid,
                Asset.is_active == True,  # noqa: E712
                Asset.rights_holder_id == body.rights_holder_id,
            )
        )
        if result.scalar_one_or_none() is None:
            invalid_ids.append(asset_id_str)

    if invalid_ids:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unknown or mismatched asset IDs: {invalid_ids}",
        )

    return {"valid": True}


# ---------------------------------------------------------------------------
# GET /assets/download/{token_id}  (local-storage presigned URL handler)
# ---------------------------------------------------------------------------


@app.get("/assets/download/{token_id}")
async def download_asset(
    token_id: str,
    db: AsyncSession = Depends(get_db),
    store: AssetStore = Depends(get_store),
):
    """Redeem a single-use download token and stream the file."""
    try:
        token_uuid = uuid.UUID(token_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid token format")

    result = await db.execute(select(UsedToken).where(UsedToken.id == token_uuid))
    token = result.scalar_one_or_none()

    if token is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Token not found")

    now = datetime.now(timezone.utc)

    if token.redeemed:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token already redeemed")

    # Compare aware datetimes; expires_at may be stored without tz in SQLite
    expires_at = token.expires_at
    if expires_at.tzinfo is None:
        expires_at = expires_at.replace(tzinfo=timezone.utc)
    if now > expires_at:
        raise HTTPException(status_code=status.HTTP_410_GONE, detail="Token has expired")

    # Mark redeemed before serving (prevents race-condition double-use)
    token.redeemed = True
    token.redeemed_at = now
    await db.commit()

    # Fetch asset metadata for Content-Type
    asset_result = await db.execute(select(Asset).where(Asset.id == token.asset_id))
    asset = asset_result.scalar_one_or_none()
    content_type = asset.content_type if asset else "application/octet-stream"
    filename = asset.filename if asset else "download"

    file_bytes = await store.read_file(str(token.asset_id))
    return Response(
        content=file_bytes,
        media_type=content_type,
        headers={"Content-Disposition": f'attachment; filename="{filename}"'},
    )
