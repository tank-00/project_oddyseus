"""Tests for the DCT spread-spectrum watermark encoder/decoder.

Coverage
--------
- Round-trip encode → decode on a synthetic PNG (no compression loss)
- Robustness: encode → JPEG-compress to quality=75 → decode still recovers ID
- POST /v1/post-generate returns watermarked image + updates transaction
- POST /v1/detect identifies the watermark and returns transaction metadata
- POST /v1/detect on an unwatermarked image returns {found: false}
"""

from __future__ import annotations

import base64
import io
import uuid

import pytest
import pytest_asyncio
from PIL import Image
import numpy as np

import sys, os
# Ensure gateway root is on sys.path so "import watermark" resolves
sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))

import watermark as wm


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_test_image(width: int = 128, height: int = 128, fmt: str = "PNG") -> bytes:
    """Create a synthetic RGB image with visible structure (not solid colour)."""
    rng = np.random.default_rng(42)
    arr = rng.integers(30, 220, size=(height, width, 3), dtype=np.uint8)
    # Add smooth gradient so DCT mid-frequencies carry energy
    for i in range(height):
        arr[i, :, 0] = np.clip(arr[i, :, 0].astype(int) + i, 0, 255)
    buf = io.BytesIO()
    Image.fromarray(arr, "RGB").save(buf, format=fmt)
    return buf.getvalue()


def _jpeg_recompress(image_bytes: bytes, quality: int) -> bytes:
    """Re-save image as JPEG at *quality* to simulate platform recompression."""
    buf = io.BytesIO()
    Image.open(io.BytesIO(image_bytes)).convert("RGB").save(buf, format="JPEG", quality=quality)
    return buf.getvalue()


# ---------------------------------------------------------------------------
# Unit tests — watermark module
# ---------------------------------------------------------------------------

class TestWatermarkRoundTrip:
    def test_encode_returns_bytes(self):
        gid = uuid.uuid4()
        raw = _make_test_image()
        result = wm.encode(raw, gid)
        assert isinstance(result, bytes)
        assert len(result) > 0

    def test_encode_decode_png_roundtrip(self):
        """Encode into PNG → decode (no JPEG loss) → must recover the same ID."""
        gid = uuid.uuid4()
        raw = _make_test_image(fmt="PNG")
        watermarked = wm.encode(raw, gid)

        recovered = wm.decode(watermarked, [gid])
        assert recovered == gid

    def test_encode_decode_wrong_id_returns_none(self):
        """A different candidate ID must NOT be returned."""
        gid = uuid.uuid4()
        wrong_id = uuid.uuid4()
        raw = _make_test_image()
        watermarked = wm.encode(raw, gid)

        # Only pass the wrong candidate
        recovered = wm.decode(watermarked, [wrong_id])
        assert recovered is None

    def test_encode_decode_correct_id_among_decoys(self):
        """Correct ID is recovered even when mixed with many decoy candidates."""
        gid = uuid.uuid4()
        decoys = [uuid.uuid4() for _ in range(50)]
        candidates = decoys[:25] + [gid] + decoys[25:]

        raw = _make_test_image()
        watermarked = wm.encode(raw, gid)

        recovered = wm.decode(watermarked, candidates)
        assert recovered == gid

    def test_decode_empty_candidates_returns_none(self):
        raw = _make_test_image()
        gid = uuid.uuid4()
        watermarked = wm.encode(raw, gid)
        assert wm.decode(watermarked, []) is None

    def test_decode_unwatermarked_image_returns_none(self):
        raw = _make_test_image()
        gid = uuid.uuid4()
        # Pass the raw (un-watermarked) image with the candidate
        result = wm.decode(raw, [gid])
        assert result is None


class TestWatermarkJpegRobustness:
    def test_survives_jpeg_quality_75(self):
        """Core robustness requirement: watermark must survive JPEG 75 recompression."""
        gid = uuid.uuid4()
        raw = _make_test_image(width=256, height=256)
        watermarked = wm.encode(raw, gid)

        recompressed = _jpeg_recompress(watermarked, quality=75)
        recovered = wm.decode(recompressed, [gid])
        assert recovered == gid, (
            "Watermark was NOT recovered after JPEG quality=75 recompression. "
            "Consider increasing DELTA in watermark.py."
        )

    def test_survives_jpeg_quality_75_with_decoys(self):
        """Correct ID is still recovered after recompression even with decoys."""
        gid = uuid.uuid4()
        decoys = [uuid.uuid4() for _ in range(20)]
        candidates = [gid] + decoys

        raw = _make_test_image(width=256, height=256)
        watermarked = wm.encode(raw, gid)
        recompressed = _jpeg_recompress(watermarked, quality=75)

        recovered = wm.decode(recompressed, candidates)
        assert recovered == gid


# ---------------------------------------------------------------------------
# Integration tests — API endpoints
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_post_generate_returns_watermarked_image(client, auth_token, db_session):
    """POST /v1/post-generate: happy path — returns watermarked image as base64."""
    import time
    from app.jwt_utils import encode as jwt_encode
    from app.models import Transaction, Decision
    import uuid as _uuid

    SECRET_KEY = "test-secret-key"

    # Insert a transaction directly
    request_id = _uuid.uuid4()
    txn = Transaction(
        client_id="test-tool",
        end_user_id="user-1",
        rights_holder_id="rh-1",
        request_id=request_id,
        decision=Decision.approve,
        metadata_={"rights_holder_id": "rh-1", "use_type": "editorial"},
    )
    db_session.add(txn)
    await db_session.commit()

    # Build a valid session token
    import os
    secret = os.getenv("SHIELD_JWT_SECRET", "dev-secret")
    session_token = jwt_encode(
        {"request_id": str(request_id), "asset_ids": [], "exp": int(time.time()) + 300},
        secret,
        algorithm="HS256",
    )

    raw_image = _make_test_image(128, 128)
    image_b64 = base64.b64encode(raw_image).decode()

    resp = await client.post(
        "/v1/post-generate",
        json={"session_token": session_token, "image": image_b64},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["generation_id"] == str(request_id)
    assert "image" in data
    assert "output_hash" in data

    # Returned image should decode as a valid JPEG
    returned_bytes = base64.b64decode(data["image"])
    img = Image.open(io.BytesIO(returned_bytes))
    assert img.format == "JPEG"


@pytest.mark.asyncio
async def test_post_generate_idempotency_guard(client, auth_token, db_session):
    """POST /v1/post-generate: second call returns 409."""
    import time, os
    from app.jwt_utils import encode as jwt_encode
    from app.models import Transaction, Decision
    import uuid as _uuid

    request_id = _uuid.uuid4()
    txn = Transaction(
        client_id="test-tool",
        end_user_id="user-1",
        rights_holder_id="rh-1",
        request_id=request_id,
        decision=Decision.approve,
        watermarked=True,   # already processed
        metadata_={},
    )
    db_session.add(txn)
    await db_session.commit()

    secret = os.getenv("SHIELD_JWT_SECRET", "dev-secret")
    session_token = jwt_encode(
        {"request_id": str(request_id), "asset_ids": [], "exp": int(time.time()) + 300},
        secret, algorithm="HS256",
    )

    raw_image = _make_test_image(64, 64)
    resp = await client.post(
        "/v1/post-generate",
        json={"session_token": session_token, "image": base64.b64encode(raw_image).decode()},
        headers={"Authorization": f"Bearer {auth_token}"},
    )
    assert resp.status_code == 409


@pytest.mark.asyncio
async def test_detect_finds_watermark(client, db_session):
    """POST /v1/detect: watermarked image → found=True with metadata."""
    import time, os, hashlib
    from datetime import datetime, timezone
    from app.jwt_utils import encode as jwt_encode
    from app.models import Transaction, Decision
    import uuid as _uuid

    # Create a transaction and encode a watermark
    request_id = _uuid.uuid4()
    raw_image = _make_test_image(128, 128)
    watermarked = wm.encode(raw_image, request_id)
    output_hash = hashlib.sha256(watermarked).hexdigest()

    txn = Transaction(
        client_id="test-tool",
        end_user_id="user-detect",
        rights_holder_id="rh-detect",
        request_id=request_id,
        decision=Decision.approve,
        watermarked=True,
        output_hash=output_hash,
        completed_at=datetime.now(timezone.utc),
        metadata_={"rights_holder_id": "rh-detect", "use_type": "fan"},
    )
    db_session.add(txn)
    await db_session.commit()

    resp = await client.post(
        "/v1/detect",
        json={"image": base64.b64encode(watermarked).decode()},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["found"] is True
    assert data["generation_id"] == str(request_id)
    assert data["transaction"]["end_user_id"] == "user-detect"


@pytest.mark.asyncio
async def test_detect_unwatermarked_returns_not_found(client):
    """POST /v1/detect: plain image → found=False."""
    raw_image = _make_test_image(128, 128)
    resp = await client.post(
        "/v1/detect",
        json={"image": base64.b64encode(raw_image).decode()},
    )
    assert resp.status_code == 200
    assert resp.json()["found"] is False
