"""Shield SDK — ShieldClient implementation.

Handles OAuth 2.0 token acquisition and silent refresh, then wraps every
Shield gateway endpoint in a simple, typed Python API.
"""

from __future__ import annotations

import base64
import time
from typing import Any

import requests

from .exceptions import ShieldAPIError, ShieldAuthError, ShieldEscalateError, ShieldRejectedError
from .models import AssetURL, DetectResult, PostGenerateResult, PreGenerateResult

# Refresh the token this many seconds before it actually expires
_TOKEN_REFRESH_BUFFER_SECS = 60


class ShieldClient:
    """Authenticated client for the Shield gateway API.

    Parameters
    ----------
    base_url:
        Root URL of the Shield gateway, e.g. ``http://localhost:8000``.
    client_id:
        OAuth 2.0 client identifier issued by your Shield deployment.
    client_secret:
        Matching client secret.

    Example
    -------
    >>> client = ShieldClient("http://localhost:8000", "my-tool", "s3cr3t")
    >>> result = client.pre_generate(
    ...     rights_holder_id="acme-corp",
    ...     prompt="A hero in a city",
    ...     content_categories=["fantasy"],
    ...     use_type="editorial",
    ...     asset_ids=[],
    ... )
    >>> print(result.session_token)
    """

    def __init__(self, base_url: str, client_id: str, client_secret: str) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self._token: str | None = None
        self._token_expires_at: float = 0.0
        self._session = requests.Session()

    # ------------------------------------------------------------------
    # Token management
    # ------------------------------------------------------------------

    def _refresh_token(self) -> None:
        resp = self._session.post(
            f"{self.base_url}/auth/token",
            data={
                "client_id": self.client_id,
                "client_secret": self.client_secret,
            },
        )
        if resp.status_code != 200:
            raise ShieldAuthError(
                f"Token acquisition failed ({resp.status_code}): {resp.text}"
            )
        data = resp.json()
        self._token = data["access_token"]
        self._token_expires_at = time.time() + data.get("expires_in", 3600)

    def _ensure_token(self) -> None:
        if self._token is None or time.time() >= self._token_expires_at - _TOKEN_REFRESH_BUFFER_SECS:
            self._refresh_token()

    def _auth_headers(self) -> dict[str, str]:
        self._ensure_token()
        return {"Authorization": f"Bearer {self._token}"}

    # ------------------------------------------------------------------
    # Internal request helper
    # ------------------------------------------------------------------

    def _post(self, path: str, json: dict[str, Any], auth: bool = True) -> dict[str, Any]:
        headers = self._auth_headers() if auth else {}
        resp = self._session.post(f"{self.base_url}{path}", json=json, headers=headers)
        return self._handle_response(resp)

    def _get(self, path: str, params: dict[str, Any] | None = None) -> Any:
        resp = self._session.get(
            f"{self.base_url}{path}",
            params=params,
            headers=self._auth_headers(),
        )
        return self._handle_response(resp)

    @staticmethod
    def _handle_response(resp: requests.Response) -> Any:
        if resp.status_code == 200:
            return resp.json()
        detail = resp.text
        try:
            detail = resp.json().get("detail", detail)
        except Exception:
            pass
        if resp.status_code == 403:
            raise ShieldRejectedError(f"Generation rejected: {detail}", reason=detail)
        if resp.status_code == 202:
            raise ShieldEscalateError(f"Generation escalated: {detail}", reason=detail)
        if resp.status_code in (401, 403):
            raise ShieldAuthError(f"Authentication error ({resp.status_code}): {detail}")
        raise ShieldAPIError(
            f"Gateway error ({resp.status_code}): {detail}",
            status_code=resp.status_code,
        )

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def pre_generate(
        self,
        rights_holder_id: str,
        prompt: str,
        content_categories: list[str],
        use_type: str,
        asset_ids: list[str],
    ) -> PreGenerateResult:
        """Request generation permission from the Shield policy engine.

        Parameters
        ----------
        rights_holder_id:
            Identifier of the rights holder whose policy governs this request.
        prompt:
            The generation prompt (stored in the transaction log).
        content_categories:
            List of content category tags for the prompt (e.g. ``["fantasy"]``).
        use_type:
            Intended use of the generated image (e.g. ``"editorial"``, ``"commercial"``).
        asset_ids:
            UUIDs of licensed assets to be used in generation, or empty list.

        Returns
        -------
        PreGenerateResult
            Contains the ``session_token`` needed for subsequent calls.

        Raises
        ------
        ShieldRejectedError
            The policy engine rejected the request.
        ShieldEscalateError
            The policy engine flagged the request for human review.
        """
        data = self._post(
            "/v1/pre-generate",
            json={
                "rights_holder_id": rights_holder_id,
                "prompt": prompt,
                "content_categories": content_categories,
                "use_type": use_type,
                "asset_ids": asset_ids,
            },
        )
        return PreGenerateResult(
            decision=data["decision"],
            session_token=data["session_token"],
            reason=data.get("reason", ""),
            asset_ids=asset_ids,
        )

    def get_assets(self, session_token: str, asset_ids: list[str]) -> list[AssetURL]:
        """Fetch presigned download URLs for approved licensed assets.

        Parameters
        ----------
        session_token:
            Token returned by :meth:`pre_generate`.
        asset_ids:
            Subset of approved asset IDs to retrieve.

        Returns
        -------
        list[AssetURL]
            One entry per asset ID with a presigned ``url`` and ``expires_at``.
        """
        data = self._post(
            "/v1/get-assets",
            json={"session_token": session_token, "asset_ids": asset_ids},
        )
        return [
            AssetURL(
                asset_id=asset_id,
                url=info if isinstance(info, str) else info.get("url", ""),
                expires_at=info.get("expires_at") if isinstance(info, dict) else None,
            )
            for asset_id, info in data.items()
        ]

    def post_generate(self, session_token: str, image_bytes: bytes) -> PostGenerateResult:
        """Watermark a generated image and finalise the transaction.

        Parameters
        ----------
        session_token:
            Token returned by :meth:`pre_generate`.
        image_bytes:
            Raw bytes of the generated image (JPEG or PNG).

        Returns
        -------
        PostGenerateResult
            ``watermarked_image_bytes`` is the branded output ready for delivery.
        """
        image_b64 = base64.b64encode(image_bytes).decode()
        data = self._post(
            "/v1/post-generate",
            json={"session_token": session_token, "image": image_b64},
        )
        return PostGenerateResult(
            watermarked_image_bytes=base64.b64decode(data["image"]),
            generation_id=data["generation_id"],
            output_hash=data.get("output_hash", ""),
        )

    def decode_watermark(self, image_bytes: bytes) -> DetectResult:
        """Detect a Shield watermark and retrieve provenance metadata.

        This endpoint is public — no credentials are required on the server
        side, but the SDK still sends the auth token for consistency.

        Parameters
        ----------
        image_bytes:
            Raw bytes of the image to inspect.

        Returns
        -------
        DetectResult
            ``found=True`` with ``generation_id`` and ``transaction_metadata``
            if a watermark is detected; ``found=False`` otherwise.
        """
        image_b64 = base64.b64encode(image_bytes).decode()
        data = self._post("/v1/detect", json={"image": image_b64}, auth=False)
        return DetectResult(
            found=data.get("found", False),
            generation_id=data.get("generation_id"),
            transaction_metadata=data.get("transaction"),
        )

    def list_transactions(self, rights_holder_id: str) -> list[dict]:
        """Return the last 100 transactions for *rights_holder_id*.

        Parameters
        ----------
        rights_holder_id:
            The rights holder to filter by.

        Returns
        -------
        list[dict]
            Each dict contains ``request_id``, ``decision``, ``created_at``, etc.
        """
        return self._get("/v1/transactions", params={"rights_holder_id": rights_holder_id})
