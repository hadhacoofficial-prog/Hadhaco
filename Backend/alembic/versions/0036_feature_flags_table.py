"""Create feature_flags table and seed complimentary_gift_enabled.

The `FeatureFlag` model (app/modules/settings/models.py) and its admin/public
routers already existed in code, but no migration ever created the backing
table in the actual Postgres schema (only a parallel, disconnected
`Backend/supabase/sql/018_feature_flags.sql` reference file did). This adds
the table and seeds `complimentary_gift_enabled=true` so the already-live
complimentary-gift checkout feature keeps working until an admin explicitly
disables it from the new Store Settings page.

Revision ID: 0036_feature_flags_table
Revises: 0035_phase3_cutover_products_collections_categories
Create Date: 2026-07-08
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0036_feature_flags_table"
down_revision: str | None = "0035_phase3_cutover_products_collections_categories"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    # Some environments already have this table (it was provisioned directly
    # via Backend/supabase/sql/018_feature_flags.sql, outside the alembic
    # chain) — guard so this migration is safe on both fresh and pre-seeded
    # databases.
    conn = op.get_bind()
    inspector = sa.inspect(conn)
    if "feature_flags" not in inspector.get_table_names():
        op.create_table(
            "feature_flags",
            sa.Column("key", sa.Text(), primary_key=True),
            sa.Column("value", sa.Boolean(), nullable=False, server_default=sa.false()),
            sa.Column("description", sa.Text(), nullable=True),
            sa.Column("updated_by", UUID(as_uuid=True), nullable=True),
            sa.Column(
                "updated_at",
                sa.DateTime(timezone=True),
                nullable=False,
                server_default=sa.text("now()"),
            ),
        )
    op.execute("""
        INSERT INTO feature_flags (key, value, description)
        VALUES (
            'complimentary_gift_enabled',
            true,
            'Show complimentary gift option at checkout'
        )
        ON CONFLICT (key) DO NOTHING;
        """)


def downgrade() -> None:
    # Never drop the table here — on environments where it pre-existed
    # outside this migration's control, dropping it would destroy state this
    # migration didn't create. Just remove the row this migration seeded.
    op.execute("DELETE FROM feature_flags WHERE key = 'complimentary_gift_enabled';")
