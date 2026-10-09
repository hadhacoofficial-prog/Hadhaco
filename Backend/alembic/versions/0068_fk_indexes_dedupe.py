"""Cover unindexed foreign keys and drop duplicate indexes.

Driven by the Supabase performance advisors (checked 2026-10-10):

  * ``unindexed_foreign_keys`` — every FK below lacked a covering index, so
    deleting/updating a parent row (or joining on the FK) scanned the child
    table. All tables are small today; this keeps it that way as they grow.
  * ``duplicate_index`` — ``coupon_usages`` and ``notification_logs`` each had
    two identical btree indexes on ``user_id``. One of each pair is dropped
    (the surviving names match the ORM models).

``analytics_events`` is partitioned: CREATE INDEX CONCURRENTLY is not
supported on a partitioned parent, so the parent index (which Postgres
propagates to every existing and future partition) is created in the normal
transaction. The table holds no rows in the parent and ~57 kB per partition,
so the lock is momentary.

Row level security policies flagged by the same advisor are intentionally NOT
touched: migration 0067 revoked every ``anon``/``authenticated`` privilege on
``public``, so those policies are unreachable and rewriting them is pure risk.

Additive/re-runnable (IF NOT EXISTS / IF EXISTS); no rows are modified.

Revision ID: 0068_fk_indexes_dedupe
Revises: 0067_supabase_data_api_hardening
Create Date: 2026-10-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0068_fk_indexes_dedupe"
down_revision: str | None = "0067_supabase_data_api_hardening"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_FK_INDEXES: tuple[tuple[str, str], ...] = (
    ("app_settings", "updated_by"),
    ("banners", "created_by"),
    ("cart_items", "variant_id"),
    ("categories", "primary_image_id"),
    ("cms_cache_version", "invalidated_by"),
    ("cms_media", "uploaded_by"),
    ("cms_pages", "created_by"),
    ("cms_publish_log", "admin_id"),
    ("cms_version_history", "published_by"),
    ("collections", "primary_image_id"),
    ("feature_flags", "updated_by"),
    ("fraud_signals", "resolved_by"),
    ("images", "uploaded_by"),
    ("inventory_transactions", "performed_by"),
    ("landing_sections", "created_by"),
    ("landing_sections", "published_by"),
    ("profiles", "primary_image_id"),
    ("review_votes", "user_id"),
    ("reviews", "order_id"),
    ("wishlist_items", "variant_id"),
)

# (index dropped, table, column) — the other identical index is kept.
_DUPLICATES: tuple[tuple[str, str, str], ...] = (
    ("idx_coupon_usages_user", "coupon_usages", "user_id"),
    ("idx_notif_logs_user", "notification_logs", "user_id"),
)


def _name(table: str, column: str) -> str:
    return f"idx_{table}_{column}_fk"


def upgrade() -> None:
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_analytics_events_category_id_fk "
        "ON analytics_events (category_id)"
    )
    for table, column in _FK_INDEXES:
        with op.get_context().autocommit_block():
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {_name(table, column)} "
                f"ON {table} ({column})"
            )
    for index, _table, _column in _DUPLICATES:
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {index}")


def downgrade() -> None:
    for index, table, column in _DUPLICATES:
        with op.get_context().autocommit_block():
            op.execute(
                f"CREATE INDEX CONCURRENTLY IF NOT EXISTS {index} "
                f"ON {table} ({column})"
            )
    for table, column in reversed(_FK_INDEXES):
        with op.get_context().autocommit_block():
            op.execute(f"DROP INDEX CONCURRENTLY IF EXISTS {_name(table, column)}")
    op.execute("DROP INDEX IF EXISTS idx_analytics_events_category_id_fk")
