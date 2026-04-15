"""DCT spread-spectrum watermark encoder / decoder.

Embeds a 128-bit generation_id (UUID) into the luma channel of an image
using frequency-domain (DCT) modifications.  The watermark is visually
imperceptible and survives JPEG compression to ~75% quality.

Algorithm
---------
encode:
  1. Convert image to YCbCr; operate on the Y (luma) channel.
  2. Divide Y into non-overlapping 8×8 blocks.
  3. Apply 2-D DCT (norm='ortho') to each block via scipy.fft.dctn.
  4. Use the generation_id as a PRNG seed to generate a spread-spectrum
     PN sequence of ±1 values — one per (block, mid-frequency coefficient).
  5. Add DELTA × PN[i] to each selected coefficient.
  6. Apply inverse DCT, reconstruct image, return JPEG bytes (quality=92).

decode:
  1. Extract all mid-frequency DCT coefficients from the Y channel.
  2. For each candidate generation_id compute the normalised dot product
     between the coefficients vector and the candidate's PN sequence.
  3. Return the candidate whose correlation exceeds THRESHOLD; else None.

  NOTE: This MVP brute-forces up to 10 000 transaction IDs.
  TODO (scale): build an ANN index over PN projections, or use a
  Bloom-filter / LSH lookup, to reduce O(N×M) to O(N log M).
"""

from __future__ import annotations

import io
import uuid as _uuid_mod
from typing import Sequence

import numpy as np
from PIL import Image
from scipy.fft import dctn, idctn

# ---------------------------------------------------------------------------
# Tunable constants
# ---------------------------------------------------------------------------

BLOCK_SIZE: int = 8

# Watermark embedding strength.  Must be large enough that the signal survives
# JPEG quantisation at quality ≥ 75.  At quality 75, mid-frequency luminance
# quantisation steps are roughly 8–16 luma units; DELTA=25 ensures the
# modification exceeds the round-trip rounding error with margin.
DELTA: float = 25.0

# Normalised-correlation threshold for a positive detection.
# True-watermark correlation  ≈ DELTA (ideal) / normaliser.
# False-positive correlation  ≈ 0 ± tiny noise.
# We threshold at 40 % of DELTA after normalisation (see _correlate).
THRESHOLD: float = 0.4

# Mid-frequency DCT coefficient positions within an 8×8 block (row, col).
# These sit in the "AC middle band" of the zigzag scan — robust against both
# spatial artefacts (low-freq) and JPEG quantisation noise (high-freq).
MID_FREQ_POSITIONS: list[tuple[int, int]] = [
    (1, 2), (2, 1), (3, 0),
    (2, 2), (1, 3), (0, 4),
    (1, 4), (2, 3), (3, 2),
    (4, 1), (3, 3), (2, 4),
]


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _pn_sequence(generation_id: _uuid_mod.UUID, length: int) -> np.ndarray:
    """Return a reproducible ±1 spread-spectrum sequence seeded by *generation_id*."""
    rng = np.random.default_rng(generation_id.int)
    return rng.choice(np.array([-1.0, 1.0]), size=length)


def _extract_coefficients(y_channel: np.ndarray) -> np.ndarray:
    """Return a 1-D array of mid-frequency DCT coefficients from all 8×8 blocks."""
    h, w = y_channel.shape
    n_bh = h // BLOCK_SIZE
    n_bw = w // BLOCK_SIZE
    n_per_block = len(MID_FREQ_POSITIONS)
    coeffs = np.empty(n_bh * n_bw * n_per_block, dtype=np.float64)
    idx = 0
    for bi in range(n_bh):
        for bj in range(n_bw):
            r0 = bi * BLOCK_SIZE
            c0 = bj * BLOCK_SIZE
            block = y_channel[r0 : r0 + BLOCK_SIZE, c0 : c0 + BLOCK_SIZE]
            dct_block = dctn(block, norm="ortho")
            for r, c in MID_FREQ_POSITIONS:
                coeffs[idx] = dct_block[r, c]
                idx += 1
    return coeffs


def _correlate(coeffs: np.ndarray, generation_id: _uuid_mod.UUID) -> float:
    """Normalised dot product between *coeffs* and the PN sequence for *generation_id*.

    Returns a value close to DELTA for the correct ID, close to 0 otherwise.
    """
    pn = _pn_sequence(generation_id, len(coeffs))
    return float(np.dot(coeffs, pn) / len(coeffs))


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def encode(image_bytes: bytes, generation_id: _uuid_mod.UUID) -> bytes:
    """Embed *generation_id* into *image_bytes* and return JPEG bytes (quality=92).

    Parameters
    ----------
    image_bytes:
        Raw bytes of a JPEG or PNG image.
    generation_id:
        UUID used both as the watermark payload and PRNG seed.

    Returns
    -------
    bytes
        JPEG-encoded watermarked image.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("YCbCr")
    arr = np.array(img, dtype=np.float64)  # shape (H, W, 3)
    y = arr[:, :, 0]

    h, w = y.shape
    n_bh = h // BLOCK_SIZE
    n_bw = w // BLOCK_SIZE
    n_per_block = len(MID_FREQ_POSITIONS)
    n_coeffs = n_bh * n_bw * n_per_block

    if n_bh == 0 or n_bw == 0:
        raise ValueError(
            f"Image too small for watermarking: {w}×{h} (need at least {BLOCK_SIZE}×{BLOCK_SIZE})"
        )

    pn = _pn_sequence(generation_id, n_coeffs)
    pn_idx = 0

    y_wm = y.copy()
    for bi in range(n_bh):
        for bj in range(n_bw):
            r0 = bi * BLOCK_SIZE
            c0 = bj * BLOCK_SIZE
            block = y_wm[r0 : r0 + BLOCK_SIZE, c0 : c0 + BLOCK_SIZE]
            dct_block = dctn(block, norm="ortho")
            for r, c in MID_FREQ_POSITIONS:
                dct_block[r, c] += DELTA * pn[pn_idx]
                pn_idx += 1
            y_wm[r0 : r0 + BLOCK_SIZE, c0 : c0 + BLOCK_SIZE] = np.clip(
                idctn(dct_block, norm="ortho"), 0.0, 255.0
            )

    arr[:, :, 0] = y_wm
    result = Image.fromarray(arr.astype(np.uint8), mode="YCbCr").convert("RGB")
    buf = io.BytesIO()
    result.save(buf, format="JPEG", quality=92)
    return buf.getvalue()


def decode(
    image_bytes: bytes,
    candidate_ids: Sequence[_uuid_mod.UUID],
) -> _uuid_mod.UUID | None:
    """Recover the generation_id watermarked into *image_bytes*, or return None.

    Parameters
    ----------
    image_bytes:
        Raw bytes of the (possibly JPEG-recompressed) image to inspect.
    candidate_ids:
        Ordered iterable of UUIDs to test.  The function returns the first
        candidate whose correlation exceeds THRESHOLD.  For the MVP, pass
        the last 10 000 transaction request_ids from the database.

        TODO (scale): replace brute-force with an ANN / LSH index so that
        this runs in sub-linear time for large transaction volumes.

    Returns
    -------
    uuid.UUID | None
        The matched generation_id, or None if no match is found.
    """
    img = Image.open(io.BytesIO(image_bytes)).convert("YCbCr")
    y = np.array(img, dtype=np.float64)[:, :, 0]

    coeffs = _extract_coefficients(y)

    best_id: _uuid_mod.UUID | None = None
    best_corr: float = DELTA * THRESHOLD  # minimum acceptable correlation

    for gid in candidate_ids:
        corr = _correlate(coeffs, gid)
        if corr > best_corr:
            best_corr = corr
            best_id = gid

    return best_id
