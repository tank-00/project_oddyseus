"""POST /v1/pre-generate — policy-gated generation pre-check.

Calls the policy service, logs the transaction, then:
  approve  → 200 with a short-lived session_token JWT
  reject   → 403 with the policy reason
  escalate → 202 with the policy reason (generation should pause)
"""

import os
import time
import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from .auth import require_auth
from .database import get_db
from .jwt_utils import encode as jwt_encode
from .models import Decision, IdentityClaims, Transaction

POLICY_SERVICE_URL = os.getenv("POLICY_SERVICE_URL", "http://policy:8001")
SECRET_KEY = os.getenv("SHIELD_JWT_SECRET", "dev-secret")
SESSION_TOKEN_EXPIRE_SECONDS = 300

router = APIRouter(prefix="/v1", tags=["generation"])


class PreGenerateRequest(BaseModel):
    rights_holder_id: str
    prompt: str
    content_categories: list[str]
    use_type: str
    asset_ids: list[str]


async def _call_policy_service(payload: dict) -> dict:
    """HTTP call to the internal policy service /evaluate endpoint."""
    async with httpx.AsyncClient() as http:
        resp = await http.post(f"{POLICY_SERVICE_URL}/evaluate", json=payload)
        resp.raise_for_status()
        return resp.json()


@router.post("/pre-generate")
async def pre_generate(
    body: PreGenerateRequest,
    claims: IdentityClaims = Depends(require_auth),
    db: AsyncSession = Depends(get_db),
):
    request_id = str(uuid.uuid4())

    policy_data = await _call_policy_service(
        {
            "rights_holder_id": body.rights_holder_id,
            "content_categories": body.content_categories,
            "use_type": body.use_type,
            "identity": {
                "tool_provider_id": claims.tool_provider_id,
                "client_app_id": claims.client_app_id,
                "end_user_id": claims.end_user_id,
            },
            "request_id": request_id,
        }
    )

    decision: str = policy_data["decision"]
    reason: str = policy_data["reason"]
    matched_rule: str = policy_data.get("matched_rule", "unknown")

    # Persist the transaction regardless of decision
    txn = Transaction(
        client_id=claims.client_id,
        end_user_id=claims.end_user_id,
        request_id=uuid.UUID(request_id),
        decision=Decision(decision),
        metadata_={
            "rights_holder_id": body.rights_holder_id,
            "use_type": body.use_type,
            "matched_rule": matched_rule,
        },
    )
    db.add(txn)
    await db.commit()

    if decision == "approve":
        session_token = jwt_encode(
            {
                "request_id": request_id,
                "asset_ids": body.asset_ids,
                "exp": int(time.time()) + SESSION_TOKEN_EXPIRE_SECONDS,
            },
            SECRET_KEY,
            algorithm="HS256",
        )
        return {
            "decision": "approve",
            "session_token": session_token,
            "reason": reason,
            "request_id": request_id,
        }

    if decision == "reject":
        raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail=reason)

    # escalate
    raise HTTPException(status_code=status.HTTP_202_ACCEPTED, detail=reason)
