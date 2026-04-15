"""GET /v1/transactions — return recent transactions for a rights holder.

Protected by require_auth().  Returns the last 100 transactions for the
specified rights_holder_id, ordered newest first.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import require_auth
from .database import get_db
from .models import IdentityClaims, Transaction

router = APIRouter(prefix="/v1", tags=["transactions"])


@router.get("/transactions")
async def list_transactions(
    rights_holder_id: str = Query(..., description="Filter by rights holder"),
    claims: IdentityClaims = Depends(require_auth),  # noqa: ARG001
    db: AsyncSession = Depends(get_db),
):
    """Return the last 100 transactions for *rights_holder_id*, newest first."""
    result = await db.execute(
        select(Transaction)
        .where(Transaction.rights_holder_id == rights_holder_id)
        .order_by(Transaction.created_at.desc())
        .limit(100)
    )
    txns = result.scalars().all()

    return [
        {
            "request_id": str(t.request_id),
            "client_id": t.client_id,
            "end_user_id": t.end_user_id,
            "rights_holder_id": t.rights_holder_id,
            "use_type": (t.metadata_ or {}).get("use_type"),
            "decision": t.decision.value,
            "watermarked": t.watermarked,
            "output_hash": t.output_hash,
            "created_at": t.created_at.isoformat(),
            "completed_at": t.completed_at.isoformat() if t.completed_at else None,
        }
        for t in txns
    ]
