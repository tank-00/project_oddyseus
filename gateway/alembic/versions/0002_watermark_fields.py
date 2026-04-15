"""Add watermark fields to transactions + rights_holder_id column

Revision ID: 0002
Revises: 0001
Create Date: 2026-04-08
"""
from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0002"
down_revision: Union[str, None] = "0001"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    op.add_column(
        "transactions",
        sa.Column("rights_holder_id", sa.String(255), nullable=True),
    )
    op.create_index(
        "ix_transactions_rights_holder_id",
        "transactions",
        ["rights_holder_id"],
    )
    op.add_column(
        "transactions",
        sa.Column(
            "watermarked",
            sa.Boolean(),
            nullable=False,
            server_default=sa.false(),
        ),
    )
    op.add_column(
        "transactions",
        sa.Column("output_hash", sa.String(64), nullable=True),
    )
    op.add_column(
        "transactions",
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("transactions", "completed_at")
    op.drop_column("transactions", "output_hash")
    op.drop_column("transactions", "watermarked")
    op.drop_index("ix_transactions_rights_holder_id", table_name="transactions")
    op.drop_column("transactions", "rights_holder_id")
