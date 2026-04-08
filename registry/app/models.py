import uuid
from datetime import datetime, timezone

from pydantic import BaseModel
from sqlalchemy import BigInteger, Boolean, DateTime, ForeignKey, Integer, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column

from .database import Base


# ---------------------------------------------------------------------------
# SQLAlchemy ORM models
# ---------------------------------------------------------------------------


class Asset(Base):
    __tablename__ = "assets"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    rights_holder_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    filename: Mapped[str] = mapped_column(String(512), nullable=False)
    content_type: Mapped[str] = mapped_column(String(255), nullable=False)
    size_bytes: Mapped[int] = mapped_column(BigInteger, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)


class AssetACL(Base):
    __tablename__ = "asset_acl"

    id: Mapped[int] = mapped_column(Integer, primary_key=True)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assets.id"), nullable=False, index=True
    )
    policy_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class UsedToken(Base):
    """Tracks single-use download tokens issued by /assets/access."""

    __tablename__ = "used_tokens"

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("assets.id"), nullable=False)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False)
    redeemed: Mapped[bool] = mapped_column(Boolean, nullable=False, default=False)
    redeemed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class AssetUploadResponse(BaseModel):
    asset_id: str


class AssetAccessRequest(BaseModel):
    asset_ids: list[str]
    session_token: str


class AssetAccessResponse(BaseModel):
    urls: dict[str, str]


class AssetVerifyRequest(BaseModel):
    asset_ids: list[str]
    rights_holder_id: str
