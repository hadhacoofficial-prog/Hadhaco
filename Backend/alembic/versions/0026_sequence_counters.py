"""Add sequence_counters table for atomic ID generation (schema audit T2/R7).

Backs app.core.sequences.next_sequence_value(), which replaces the
COUNT(...)-then-format pattern used for order numbers, invoice numbers, and
support ticket numbers with a single atomic
INSERT ... ON CONFLICT DO UPDATE ... RETURNING.

Revision ID: 0026_sequence_counters
Revises: 0025_address_default_unique_and_refund_guard
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0026_sequence_counters"
down_revision: str | None = "0025_address_default_unique_and_refund_guard"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "sequence_counters",
        sa.Column("key", sa.String(100), primary_key=True),
        sa.Column("last_value", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_table("sequence_counters")
