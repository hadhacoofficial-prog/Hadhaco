"""Open review posting: admin-removal marker, several reviews per user.

Reviews now publish without moderation; admins can only remove them.

* ``reviews.admin_removed_at`` — set (with ``deleted_at``) when an admin
  removes a review. While such a row exists its author may not post new
  reviews for that product. A dedicated column, rather than reusing
  ``is_rejected``, so rows a customer deleted under the old moderation flow
  (soft-deleted + is_rejected) are never mistaken for admin removals.
* Drop the one-review-per-user-per-product unique constraint: a customer may
  now post several reviews of a product (capped in the app). The baseline
  created it unnamed (``reviews_product_id_user_id_key``); the ORM named it
  ``uq_reviews_product_user`` — both are dropped if present.
* ``idx_reviews_product_user`` replaces the constraint's index for the
  per-customer lookups (latest review, live count, block check).

Additive/re-runnable (IF [NOT] EXISTS); no rows are modified. The new column
is nullable with no default (metadata-only, no table rewrite). The index is
built in-transaction: the table is small, so the write lock is momentary.
lock_timeout makes every step fail fast instead of queueing storefront reads
behind a long-running query; the deploy retries migrations.

Downgrade restores the unique constraint, which fails if a customer already
has several reviews of one product — dedupe first in that case.

Revision ID: 0069_reviews_open_posting
Revises: 0068_fk_indexes_dedupe
Create Date: 2026-11-10
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0069_reviews_open_posting"
down_revision: str | None = "0068_fk_indexes_dedupe"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "ALTER TABLE reviews ADD COLUMN IF NOT EXISTS admin_removed_at TIMESTAMPTZ"
    )
    # Index first, so per-customer lookups are never left without one.
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_reviews_product_user "
        "ON reviews (product_id, user_id, created_at)"
    )
    op.execute(
        "ALTER TABLE reviews DROP CONSTRAINT IF EXISTS reviews_product_id_user_id_key"
    )
    op.execute("ALTER TABLE reviews DROP CONSTRAINT IF EXISTS uq_reviews_product_user")


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "ALTER TABLE reviews ADD CONSTRAINT reviews_product_id_user_id_key "
        "UNIQUE (product_id, user_id)"
    )
    op.execute("DROP INDEX IF EXISTS idx_reviews_product_user")
    op.execute("ALTER TABLE reviews DROP COLUMN IF EXISTS admin_removed_at")
