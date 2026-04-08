from fastapi import FastAPI

from .engine import evaluate
from .schemas import EvaluateRequest, EvaluateResponse

app = FastAPI(title="Shield Policy Engine", version="0.1.0")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "policy"}


@app.post("/evaluate", response_model=EvaluateResponse)
async def evaluate_policy(request: EvaluateRequest) -> EvaluateResponse:
    """Evaluate a policy request and return approve / reject / escalate."""
    return evaluate(request)
