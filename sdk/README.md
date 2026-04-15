# Shield SDK

Python client for the [Shield](../README.md) AI rights management gateway.
Handles token acquisition, silent refresh, and typed wrappers for every API endpoint.

## Installation

```bash
pip install -e ./sdk          # editable install from the monorepo root
# or
pip install shield-sdk        # once published to PyPI
```

## Quick start — full generation flow

```python
from shield_sdk import ShieldClient, ShieldRejectedError, ShieldEscalateError

client = ShieldClient(
    base_url="http://localhost:8000",   # Shield gateway URL
    client_id="my-tool",
    client_secret="my-secret",
)

# 1. Request generation permission
try:
    pre = client.pre_generate(
        rights_holder_id="acme-corp",
        prompt="A hero standing on a rooftop at dawn",
        content_categories=["fantasy", "action"],
        use_type="editorial",
        asset_ids=["asset-uuid-1", "asset-uuid-2"],
    )
except ShieldRejectedError as e:
    print(f"Blocked: {e.reason}")
    raise SystemExit(1)
except ShieldEscalateError as e:
    print(f"Needs human review: {e.reason}")
    raise SystemExit(1)

print(f"Approved — session_token: {pre.session_token[:20]}…")

# 2. Fetch presigned URLs for licensed assets (optional)
asset_urls = client.get_assets(pre.session_token, pre.asset_ids)
for a in asset_urls:
    print(f"  {a.asset_id}: {a.url}")

# 3. [Generation happens here in your own pipeline]
with open("generated.png", "rb") as f:
    raw_image_bytes = f.read()

# 4. Watermark the output and finalise the transaction
result = client.post_generate(pre.session_token, raw_image_bytes)
print(f"Watermarked — generation_id: {result.generation_id}")
print(f"SHA-256: {result.output_hash}")

# Save the watermarked image
with open("watermarked.jpg", "wb") as f:
    f.write(result.watermarked_image_bytes)

# 5. Later — verify provenance of any image
with open("watermarked.jpg", "rb") as f:
    suspect = f.read()

detection = client.decode_watermark(suspect)
if detection.found:
    print(f"Shield watermark found! generation_id: {detection.generation_id}")
    print(f"Transaction: {detection.transaction_metadata}")
else:
    print("No Shield watermark detected.")
```

## API reference

### `ShieldClient(base_url, client_id, client_secret)`

Creates an authenticated client. Tokens are acquired lazily and refreshed
automatically 60 seconds before expiry — you never need to call `/auth/token`
yourself.

### `client.pre_generate(...) → PreGenerateResult`

Calls `POST /v1/pre-generate`. Returns a `PreGenerateResult` with:
- `decision` — always `"approve"` (errors raise exceptions)
- `session_token` — pass to `get_assets` and `post_generate`
- `reason` — human-readable policy reason
- `asset_ids` — echo of the requested asset IDs

Raises `ShieldRejectedError` if the policy decision is `reject`.  
Raises `ShieldEscalateError` if the policy decision is `escalate`.

### `client.get_assets(session_token, asset_ids) → list[AssetURL]`

Calls `POST /v1/get-assets`. Returns a list of `AssetURL(asset_id, url, expires_at)`.

### `client.post_generate(session_token, image_bytes) → PostGenerateResult`

Calls `POST /v1/post-generate`. Returns a `PostGenerateResult` with:
- `watermarked_image_bytes` — JPEG bytes ready for delivery
- `generation_id` — UUID that is embedded in the watermark
- `output_hash` — SHA-256 hex digest of the watermarked bytes

### `client.decode_watermark(image_bytes) → DetectResult`

Calls `POST /v1/detect`. Returns a `DetectResult` with:
- `found` — `True` if a Shield watermark was detected
- `generation_id` — UUID of the matching transaction (if found)
- `transaction_metadata` — dict with provenance info (if found)

### `client.list_transactions(rights_holder_id) → list[dict]`

Calls `GET /v1/transactions`. Returns up to 100 recent transactions.

## Running the integration tests

```bash
# Start the local stack first
docker compose up -d

# Then run the integration tests
pip install -e ./sdk
pytest sdk/tests/ -v
```
