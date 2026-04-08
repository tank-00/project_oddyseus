"""Initial schema: clients and transactions tables with test seed

Revision ID: 0001
Revises:
Create Date: 2026-04-08
"""
from typing import Sequence, Union
import datetime

import bcrypt
import sqlalchemy as sa
from alembic import op

revision: str = "0001"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    clients = op.create_table(
        "clients",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(255), nullable=False, unique=True, index=True),
        sa.Column("client_secret_hash", sa.String(255), nullable=False),
        sa.Column("tool_provider_id", sa.String(255), nullable=False),
        sa.Column("client_app_id", sa.String(255), nullable=False),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
    )

    op.create_table(
        "transactions",
        sa.Column("id", sa.Integer(), primary_key=True),
        sa.Column("client_id", sa.String(255), nullable=False, index=True),
        sa.Column("end_user_id", sa.String(255), nullable=False),
        sa.Column(
            "request_id",
            sa.Uuid(),
            nullable=False,
            unique=True,
            server_default=sa.text("gen_random_uuid()"),
        ),
        sa.Column(
            "decision",
            sa.Enum("approve", "reject", "escalate", name="decision_enum"),
            nullable=False,
        ),
        sa.Column(
            "created_at",
            sa.DateTime(timezone=True),
            nullable=False,
            server_default=sa.func.now(),
        ),
        sa.Column("metadata", sa.JSON(), nullable=True),
    )

    # Seed the test client
    op.bulk_insert(
        clients,
        [
            {
                "client_id": "test-tool",
                "client_secret_hash": bcrypt.hashpw(b"test-secret", bcrypt.gensalt()).decode(),
                "tool_provider_id": "test-tool",
                "client_app_id": "test-app",
                "created_at": datetime.datetime.now(datetime.timezone.utc),
            }
        ],
    )


def downgrade() -> None:
    op.drop_table("transactions")
    op.drop_table("clients")
    op.execute("DROP TYPE IF EXISTS decision_enum")
