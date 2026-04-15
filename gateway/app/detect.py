"""POST /v1/detect — public endpoint to identify a Shield watermark in an image.

No authentication is required; this endpoint is intentionally public so that
anyone can verify the provenance of an image.

Flow
----
1. Decode the base64 image.
2. Fetch the last 10 000 *watermarked* transaction request_ids from the DB.
3. Run the spread-spectrum correlation decoder against all candidates.
4. If a match is found, return the generation_id + transaction metadata.
5. Otherwise return {found: false}.

Performance note
----------------
This MVP brute-forces up to 10 000 UUIDs per request.  For higher throughput,
add an ANN index over PN projections (see watermark.py TODO).
"""

from __future__ import annotations

import base64
import uuid

from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .models import Transaction

import watermark as _wm

router = APIRouter(prefix="/v1", tags=["detection"])

BRUTE_FORCE_LIMIT = 10_000


class DetectRequest(BaseModel):
    image: str  # base64-encoded bytes


@router.post("/detect")
async def detect(
    body: DetectRequest,
    db: AsyncSession = Depends(get_db),
):
    """Detect a Shield watermark and return provenance metadata."""
    # --- 1. Decode image --------------------------------------------------
    try:
        image_bytes = base64.b64decode(body.image)
    except Exception:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Invalid base64 image data")

    # --- 2. Fetch candidate IDs ------------------------------------------
    # TODO (scale): replace brute-force with an index-based lookup
    result = await db.execute(
        select(Transaction.request_id)
        .where(Transaction.watermarked == True)  # noqa: E712
        .order_by(Transaction.created_at.desc())
        .limit(BRUTE_FORCE_LIMIT)
    )
    candidate_ids: list[uuid.UUID] = [row[0] for row in result.fetchall()]

    if not candidate_ids:
        return {"found": False}

    # --- 3. Run watermark decoder ----------------------------------------
    try:
        matched_id = _wm.decode(image_bytes, candidate_ids)
    except Exception as exc:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=f"Watermark decoding failed: {exc}",
        )

    if matched_id is None:
        return {"found": False}

    # --- 4. Fetch transaction metadata ------------------------------------
    txn_result = await db.execute(
        select(Transaction).where(Transaction.request_id == matched_id)
    )
    txn: Transaction | None = txn_result.scalar_one_or_none()

    return {
        "found": True,
        "generation_id": str(matched_id),
        "transaction": {
            "request_id": str(txn.request_id),
            "client_id": txn.client_id,
            "end_user_id": txn.end_user_id,
            "rights_holder_id": txn.rights_holder_id,
            "decision": txn.decision.value,
            "created_at": txn.created_at.isoformat(),
            "completed_at": txn.completed_at.isoformat() if txn.completed_at else None,
            "output_hash": txn.output_hash,
            "metadata": txn.metadata_,
        },
    }
