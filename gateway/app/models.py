import uuid
from datetime import datetime, timezone
from enum import Enum as PyEnum

from sqlalchemy import DateTime, Enum, JSON, String, Uuid
from sqlalchemy.orm import Mapped, mapped_column
from pydantic import BaseModel

from .database import Base


class Decision(str, PyEnum):
    approve = "approve"
    reject = "reject"
    escalate = "escalate"


class Client(Base):
    __tablename__ = "clients"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(255), unique=True, nullable=False, index=True)
    client_secret_hash: Mapped[str] = mapped_column(String(255), nullable=False)
    tool_provider_id: Mapped[str] = mapped_column(String(255), nullable=False)
    client_app_id: Mapped[str] = mapped_column(String(255), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )


class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[int] = mapped_column(primary_key=True)
    client_id: Mapped[str] = mapped_column(String(255), nullable=False, index=True)
    end_user_id: Mapped[str] = mapped_column(String(255), nullable=False)
    request_id: Mapped[uuid.UUID] = mapped_column(Uuid, default=uuid.uuid4, unique=True)
    decision: Mapped[Decision] = mapped_column(Enum(Decision, name="decision_enum"), nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
    )
    metadata_: Mapped[dict | None] = mapped_column("metadata", JSON, nullable=True)


# ---------------------------------------------------------------------------
# Pydantic schemas
# ---------------------------------------------------------------------------


class IdentityClaims(BaseModel):
    client_id: str
    tool_provider_id: str
    client_app_id: str
    end_user_id: str
