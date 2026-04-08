import os
import time

from fastapi import APIRouter, Depends, Form, HTTPException, status
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer
import bcrypt
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from .database import get_db
from .jwt_utils import ExpiredSignatureError, InvalidTokenError
from .jwt_utils import decode as jwt_decode
from .jwt_utils import encode as jwt_encode
from .models import Client, IdentityClaims

SECRET_KEY = os.getenv("SHIELD_JWT_SECRET", "dev-secret")
ALGORITHM = "HS256"
TOKEN_EXPIRE_SECONDS = 3600

bearer_scheme = HTTPBearer()

router = APIRouter(prefix="/auth", tags=["auth"])


def _create_token(data: dict) -> str:
    payload = dict(data)
    payload["exp"] = int(time.time()) + TOKEN_EXPIRE_SECONDS
    return jwt_encode(payload, SECRET_KEY, algorithm=ALGORITHM)


@router.post("/token")
async def issue_token(
    client_id: str = Form(...),
    client_secret: str = Form(...),
    end_user_id: str = Form(default="unknown"),
    db: AsyncSession = Depends(get_db),
):
    """OAuth 2.0 client credentials flow — returns a signed JWT."""
    result = await db.execute(select(Client).where(Client.client_id == client_id))
    client = result.scalar_one_or_none()

    secret_matches = client and bcrypt.checkpw(
        client_secret.encode(), client.client_secret_hash.encode()
    )
    if not secret_matches:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid client credentials",
            headers={"WWW-Authenticate": "Bearer"},
        )

    token = _create_token(
        {
            "sub": client.client_id,
            "tool_provider_id": client.tool_provider_id,
            "client_app_id": client.client_app_id,
            "end_user_id": end_user_id,
        }
    )
    return {"access_token": token, "token_type": "bearer", "expires_in": TOKEN_EXPIRE_SECONDS}


async def require_auth(
    credentials: HTTPAuthorizationCredentials = Depends(bearer_scheme),
) -> IdentityClaims:
    """FastAPI dependency — validates Bearer JWT and returns decoded identity claims."""
    try:
        payload = jwt_decode(credentials.credentials, SECRET_KEY, algorithms=[ALGORITHM])
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
            headers={"WWW-Authenticate": "Bearer"},
        )
    except InvalidTokenError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Could not validate token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    client_id = payload.get("sub")
    tool_provider_id = payload.get("tool_provider_id")
    client_app_id = payload.get("client_app_id")
    end_user_id = payload.get("end_user_id")

    if not all([client_id, tool_provider_id, client_app_id, end_user_id]):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token is missing required claims",
            headers={"WWW-Authenticate": "Bearer"},
        )

    return IdentityClaims(
        client_id=client_id,
        tool_provider_id=tool_provider_id,
        client_app_id=client_app_id,
        end_user_id=end_user_id,
    )
