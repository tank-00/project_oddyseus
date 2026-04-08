from fastapi import FastAPI, Depends

from .auth import require_auth, router as auth_router
from .get_assets import router as get_assets_router
from .models import IdentityClaims
from .pre_generate import router as pre_generate_router
from .upload import router as upload_router

app = FastAPI(title="Shield Gateway", version="0.1.0")

app.include_router(auth_router)
app.include_router(pre_generate_router)
app.include_router(get_assets_router)
app.include_router(upload_router)


@app.get("/health")
async def health():
    return {"status": "ok", "service": "gateway"}


@app.get("/protected", response_model=IdentityClaims)
async def protected_route(claims: IdentityClaims = Depends(require_auth)):
    """Example protected route — returns the caller's identity claims."""
    return claims
