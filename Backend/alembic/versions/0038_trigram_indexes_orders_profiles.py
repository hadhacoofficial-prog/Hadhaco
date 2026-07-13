"""Add trigram indexes for ILIKE search paths on orders and profiles.

Orders: order_number is searched via ILIKE '%term%' in admin order listing.
Profiles: email and full_name are searched via ILIKE '%term%' in admin customer
listing.  None of these columns benefit from B-tree indexes under leading-
wildcard ILIKE; pg_trgm GIN indexes are required.

Revision ID: 0038_trigram_indexes_orders_profiles
Revises: 0037_notification_rendered_content
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0038_trigram_indexes_orders_profiles"
down_revision: str | None = "0037_notification_rendered_content"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_orders_order_number_trgm "
            "ON orders USING GIN (order_number gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_profiles_email_trgm "
            "ON profiles USING GIN (email gin_trgm_ops)"
        )
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS idx_profiles_full_name_trgm "
            "ON profiles USING GIN (full_name gin_trgm_ops)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_profiles_full_name_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_profiles_email_trgm")
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_orders_order_number_trgm")
