"""POST /v1/post-generate — watermark a generated image and finalise the transaction.

Flow
----
1. Validate the session_token (must be a valid, unexpired JWT issued by pre-generate).
2. Look up the corresponding Transaction by request_id.
3. Reject if the transaction has already been post-processed (idempotency guard).
4. Decode the base64 image, embed the watermark, and re-encode as JPEG.
5. Update the transaction: watermarked=True, output_hash, completed_at.
6. Return the watermarked image as base64 together with the generation_id.
"""

from __future__ import annotations

import base64
import hashlib
import os
import uuid
from datetime import datetime, timezone

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import require_auth
from .database import get_db
from .jwt_utils import ExpiredSignatureError, InvalidTokenError
from .jwt_utils import decode as jwt_decode
from .models import IdentityClaims, Transaction

# Import the watermark module that lives one level above the app package
import watermark as _wm

SECRET_KEY = os.getenv("SHIELD_JWT_SECRET", "dev-secret")

router = APIRouter(prefix="/v1", tags=["generation"])


class PostGenerateRequest(BaseModel):
    session_token: str
    image: str  # base64-encoded bytes


@router.post("/post-generate")
async def post_generate(
    body: PostGenerateRequest,
    claims: IdentityClaims = Depends(require_auth),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
):
    """Watermark the generated image and mark the transaction as complete."""
    # --- 1. Validate session token ----------------------------------------
    try:
        token_data = jwt_decode(body.session_token, SECRET_KEY, algorithms=["HS256"])
    except ExpiredSignatureError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Session token has expired")
    except InvalidTokenError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid session token")

    raw_request_id: str | None = token_data.get("request_id")
    if not raw_request_id:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Session token missing request_id")

    try:
        request_id = uuid.UUID(raw_request_id)
    except ValueError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Malformed request_id in token")

    # --- 2. Look up transaction -------------------------------------------
    result = await db.execute(select(Transaction).where(Transaction.request_id == request_id))
    txn: Transaction | None = result.scalar_one_or_none()
    if txn is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Transaction not found")

    # --- 3. Idempotency guard ---------------------------------------------
    if txn.watermarked:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail="Transaction has already been post-processed",
        )

    # --- 4. Decode image + embed watermark --------------------------------
    try:
        image_bytes = base64.b64decode(body.image)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 image data")

    try:
        watermarked_bytes = _wm.encode(image_bytes, txn.request_id)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Watermark encoding failed: {exc}",
        )

    # --- 5. Update transaction record -------------------------------------
    output_hash = hashlib.sha256(watermarked_bytes).hexdigest()
    txn.watermarked = True
    txn.output_hash = output_hash
    txn.completed_at = datetime.now(timezone.utc)
    await db.commit()

    # --- 6. Return watermarked image --------------------------------------
    return {
        "generation_id": str(txn.request_id),
        "output_hash": output_hash,
        "image": base64.b64encode(watermarked_bytes).decode(),
    }
