"""Policy evaluation engine.

Reads a YAML policy file for the given rights holder and evaluates rules
top-down.  First matching rule wins; default decision is escalate.
"""

import os
from pathlib import Path
from typing import Any

import yaml

from .schemas import EvaluateRequest, EvaluateResponse

POLICY_DIR = os.getenv("POLICY_DIR", "policies")


def _load_policy(rights_holder_id: str) -> dict[str, Any]:
    policy_path = Path(POLICY_DIR) / f"{rights_holder_id}.yaml"
    if not policy_path.exists():
        raise FileNotFoundError(f"No policy found for rights holder: {rights_holder_id!r}")
    with open(policy_path) as fh:
        return yaml.safe_load(fh)


def evaluate(request: EvaluateRequest) -> EvaluateResponse:
    try:
        policy = _load_policy(request.rights_holder_id)
    except FileNotFoundError as exc:
        return EvaluateResponse(
            decision="escalate",
            matched_rule="default",
            reason=str(exc),
            request_id=request.request_id,
        )

    rules: list[dict] = policy.get("rules", [])

    for rule in rules:
        rule_type = rule.get("type")

        # ------------------------------------------------------------------
        # content_category: reject if any requested category is blocked
        # ------------------------------------------------------------------
        if rule_type == "content_category":
            blocked = set(rule.get("blocked_categories", []))
            matched = set(request.content_categories) & blocked
            if matched:
                listed = ", ".join(sorted(matched))
                return EvaluateResponse(
                    decision="reject",
                    matched_rule="content_category",
                    reason=f"Content category blocked by policy: {listed}",
                    request_id=request.request_id,
                )

        # ------------------------------------------------------------------
        # use_type: map use type to a decision
        # ------------------------------------------------------------------
        elif rule_type == "use_type":
            mappings: dict[str, str] = rule.get("mappings", {})
            if request.use_type in mappings:
                decision = mappings[request.use_type]
                return EvaluateResponse(
                    decision=decision,
                    matched_rule="use_type",
                    reason=f"Use type '{request.use_type}' maps to '{decision}'",
                    request_id=request.request_id,
                )

        # ------------------------------------------------------------------
        # requester_identity: approve/reject based on client_app_id
        # ------------------------------------------------------------------
        elif rule_type == "requester_identity":
            mode: str = rule.get("mode", "open")
            ids: set[str] = set(rule.get("ids", []))
            client_app_id: str = request.identity.get("client_app_id", "")

            if mode == "open":
                return EvaluateResponse(
                    decision="approve",
                    matched_rule="requester_identity",
                    reason="Requester identity policy: open — all requesters approved",
                    request_id=request.request_id,
                )

            if mode == "allowlist":
                if client_app_id in ids:
                    return EvaluateResponse(
                        decision="approve",
                        matched_rule="requester_identity",
                        reason=f"Client app '{client_app_id}' is on the allowlist",
                        request_id=request.request_id,
                    )
                return EvaluateResponse(
                    decision="reject",
                    matched_rule="requester_identity",
                    reason=f"Client app '{client_app_id}' is not on the allowlist",
                    request_id=request.request_id,
                )

            if mode == "denylist":
                if client_app_id in ids:
                    return EvaluateResponse(
                        decision="reject",
                        matched_rule="requester_identity",
                        reason=f"Client app '{client_app_id}' is on the denylist",
                        request_id=request.request_id,
                    )
                # not on denylist — fall through to next rule

    # No rule matched
    return EvaluateResponse(
        decision="escalate",
        matched_rule="default",
        reason="No matching rule found; defaulting to escalate",
        request_id=request.request_id,
    )
