"""Integration tests for the Shield SDK.

These tests run against a live local docker-compose stack.
Start the stack with:

    docker compose up -d

then run:

    pytest sdk/tests/ -v

Environment variables (all optional, defaults match docker-compose.yml):
  SHIELD_BASE_URL    — defaults to http://localhost:8000
  SHIELD_CLIENT_ID   — defaults to test-tool
  SHIELD_CLIENT_SECRET — defaults to test-secret
  SHIELD_RH_ID       — rights_holder_id to use in tests (defaults to test-rights-holder)
"""

from __future__ import annotations

import io
import os

import pytest

SKIP_REASON = "Integration tests require a running docker-compose stack (SHIELD_INTEGRATION=1)"

# Only run when explicitly enabled, so CI doesn't fail without a live stack
pytestmark = pytest.mark.skipif(
    not os.getenv("SHIELD_INTEGRATION"),
    reason=SKIP_REASON,
)

BASE_URL = os.getenv("SHIELD_BASE_URL", "http://localhost:8000")
CLIENT_ID = os.getenv("SHIELD_CLIENT_ID", "test-tool")
CLIENT_SECRET = os.getenv("SHIELD_CLIENT_SECRET", "test-secret")
RH_ID = os.getenv("SHIELD_RH_ID", "test-rights-holder")


def _make_png_image(width: int = 128, height: int = 128) -> bytes:
    """Tiny synthetic PNG for test use (no numpy required in SDK tests)."""
    from PIL import Image
    import numpy as np

    rng = __import__("numpy").random.default_rng(0)
    arr = rng.integers(40, 200, size=(height, width, 3), dtype="uint8")
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format="PNG")
    return buf.getvalue()


@pytest.fixture(scope="module")
def client():
    from shield_sdk import ShieldClient

    return ShieldClient(BASE_URL, CLIENT_ID, CLIENT_SECRET)


class TestPreGenerate:
    def test_approved_returns_session_token(self, client):
        from shield_sdk import ShieldRejectedError, ShieldEscalateError

        result = client.pre_generate(
            rights_holder_id=RH_ID,
            prompt="A landscape",
            content_categories=["nature"],
            use_type="editorial",
            asset_ids=[],
        )
        assert result.decision == "approve"
        assert result.session_token
        assert len(result.session_token) > 10

    def test_rejected_raises_error(self, client):
        from shield_sdk import ShieldRejectedError

        with pytest.raises(ShieldRejectedError):
            client.pre_generate(
                rights_holder_id=RH_ID,
                prompt="Violence",
                content_categories=["violence"],
                use_type="editorial",
                asset_ids=[],
            )


class TestFullFlow:
    def test_pre_generate_post_generate_full_flow(self, client):
        """pre_generate → post_generate → decode_watermark round-trip."""
        # 1. pre-generate
        pre = client.pre_generate(
            rights_holder_id=RH_ID,
            prompt="A sunset",
            content_categories=["landscape"],
            use_type="fan",
            asset_ids=[],
        )
        assert pre.session_token

        # 2. post-generate (skip get_assets since no assets were requested)
        raw_image = _make_png_image()
        post = client.post_generate(pre.session_token, raw_image)
        assert post.watermarked_image_bytes
        assert post.generation_id
        assert post.output_hash

        # 3. decode watermark
        detect = client.decode_watermark(post.watermarked_image_bytes)
        assert detect.found is True
        assert detect.generation_id == post.generation_id
        assert detect.transaction_metadata is not None

    def test_decode_unwatermarked_returns_not_found(self, client):
        raw_image = _make_png_image()
        detect = client.decode_watermark(raw_image)
        assert detect.found is False


class TestTransactions:
    def test_list_transactions_returns_list(self, client):
        txns = client.list_transactions(RH_ID)
        assert isinstance(txns, list)
        if txns:
            assert "request_id" in txns[0]
            assert "decision" in txns[0]
            assert "created_at" in txns[0]
