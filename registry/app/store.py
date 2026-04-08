"""AssetStore abstraction with local-filesystem and S3 backends.

Switch via STORAGE_BACKEND env var: "local" (default) or "s3".
"""
import os
from abc import ABC, abstractmethod
from pathlib import Path

LOCAL_STORAGE_DIR = os.getenv("LOCAL_STORAGE_DIR", "./storage")
REGISTRY_BASE_URL = os.getenv("REGISTRY_BASE_URL", "http://registry:8002")


class AssetStore(ABC):
    @abstractmethod
    async def put(self, asset_id: str, file_bytes: bytes) -> None:
        """Persist file bytes under the given asset_id key."""

    @abstractmethod
    def make_download_url(self, asset_id: str, token_id: str) -> str:
        """Return a URL the client can use to download this asset."""

    async def read_file(self, asset_id: str) -> bytes:
        """Read file bytes back by asset_id (local store only)."""
        raise NotImplementedError("Direct file reads not supported for this backend")


class LocalFileStore(AssetStore):
    def __init__(self, storage_dir: str | None = None) -> None:
        self.storage_dir = Path(storage_dir or LOCAL_STORAGE_DIR)
        self.storage_dir.mkdir(parents=True, exist_ok=True)

    async def put(self, asset_id: str, file_bytes: bytes) -> None:
        (self.storage_dir / asset_id).write_bytes(file_bytes)

    def make_download_url(self, asset_id: str, token_id: str) -> str:
        base = os.getenv("REGISTRY_BASE_URL", REGISTRY_BASE_URL)
        return f"{base}/assets/download/{token_id}"

    async def read_file(self, asset_id: str) -> bytes:
        path = self.storage_dir / asset_id
        if not path.exists():
            raise FileNotFoundError(f"Asset file not found: {asset_id}")
        return path.read_bytes()


class S3Store(AssetStore):
    def __init__(self, bucket: str, prefix: str = "") -> None:
        import boto3  # lazy import — only required when using S3 backend

        self.s3 = boto3.client("s3")
        self.bucket = bucket
        self.prefix = prefix

    async def put(self, asset_id: str, file_bytes: bytes) -> None:
        import io

        self.s3.upload_fileobj(io.BytesIO(file_bytes), self.bucket, f"{self.prefix}{asset_id}")

    def make_download_url(self, asset_id: str, token_id: str) -> str:
        expiry = int(os.getenv("PRESIGN_EXPIRY_SECONDS", "60"))
        return self.s3.generate_presigned_url(
            "get_object",
            Params={"Bucket": self.bucket, "Key": f"{self.prefix}{asset_id}"},
            ExpiresIn=expiry,
        )


def get_store() -> AssetStore:
    backend = os.getenv("STORAGE_BACKEND", "local")
    if backend == "s3":
        bucket = os.getenv("S3_BUCKET", "shield-assets")
        prefix = os.getenv("S3_PREFIX", "")
        return S3Store(bucket, prefix)
    return LocalFileStore()
