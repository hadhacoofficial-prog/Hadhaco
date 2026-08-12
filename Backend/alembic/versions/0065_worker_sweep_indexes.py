"""Indexes for background worker sweep queries.

The APScheduler workers run on short cadences against the remote Supabase
instance and were doing full-table scans every tick:

  - media_generation.reclaim_stale_processing / list_pending_images (every 5s)
      WHERE status='processing' AND updated_at < cutoff
      WHERE status='pending'  AND deleted_at IS NULL ORDER BY updated_at
      -> idx_images_status_updated_at
  - notification_retry.get_pending_retries (every 30s)
      WHERE status='retrying' AND next_retry_at <= now()
      -> idx_notification_logs_status_retry_at
  - cms_publish (every 60s)
      WHERE status='scheduled' AND scheduled_at <= now()
      -> idx_landing_sections_status_scheduled_at

These three composite btree indexes turn each sweep into a small indexed
seek. Created CONCURRENTLY (autocommit blocks) so applying the migration
never blocks writes on the (potentially large) images/notification_logs
tables. All additive — no schema or data changes.

Revision ID: 0065_worker_sweep_indexes
Revises: 0064_company_config_extended_fields
Create Date: 2026-08-12
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0065_worker_sweep_indexes"
down_revision: str | None = "0064_company_config_extended_fields"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "idx_images_status_updated_at "
            "ON images (status, updated_at)"
        )
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "idx_notification_logs_status_retry_at "
            "ON notification_logs (status, next_retry_at)"
        )
    with op.get_context().autocommit_block():
        op.execute(
            "CREATE INDEX CONCURRENTLY IF NOT EXISTS "
            "idx_landing_sections_status_scheduled_at "
            "ON landing_sections (status, scheduled_at)"
        )


def downgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_landing_sections_status_scheduled_at"
        )
    with op.get_context().autocommit_block():
        op.execute(
            "DROP INDEX CONCURRENTLY IF EXISTS idx_notification_logs_status_retry_at"
        )
    with op.get_context().autocommit_block():
        op.execute("DROP INDEX CONCURRENTLY IF EXISTS idx_images_status_updated_at")
