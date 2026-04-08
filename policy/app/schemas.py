from pydantic import BaseModel


class EvaluateRequest(BaseModel):
    rights_holder_id: str
    content_categories: list[str]
    use_type: str
    identity: dict[str, str]
    request_id: str


class EvaluateResponse(BaseModel):
    decision: str  # "approve" | "reject" | "escalate"
    matched_rule: str
    reason: str
    request_id: str
