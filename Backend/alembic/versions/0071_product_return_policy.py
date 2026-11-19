"""Per-product return policy: ``is_returnable`` and ``return_window_days``.

* ``products.is_returnable`` — NOT NULL, default false. Every existing product
  therefore becomes "no return, no refund" until an admin opts it in.
* ``products.return_window_days`` — nullable; days after delivery during which
  a returnable product may be returned. NULL means the store default (7).
  A CHECK keeps stored values within 1-365.

Additive and re-runnable (IF NOT EXISTS). A constant default on ADD COLUMN is
metadata-only on PostgreSQL 11+, so there is no table rewrite. lock_timeout
makes the step fail fast instead of queueing storefront reads behind it; the
deploy retries migrations. No existing row is modified beyond receiving the
column default.

Revision ID: 0071_product_return_policy
Revises: 0070_self_auth
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0071_product_return_policy"
down_revision: str | None = "0070_self_auth"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "ALTER TABLE products "
        "ADD COLUMN IF NOT EXISTS is_returnable BOOLEAN NOT NULL DEFAULT false"
    )
    op.execute(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS return_window_days INTEGER"
    )
    op.execute(
        "ALTER TABLE products DROP CONSTRAINT IF EXISTS ck_products_return_window_days"
    )
    op.execute(
        "ALTER TABLE products ADD CONSTRAINT ck_products_return_window_days "
        "CHECK (return_window_days IS NULL OR return_window_days BETWEEN 1 AND 365)"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "ALTER TABLE products DROP CONSTRAINT IF EXISTS ck_products_return_window_days"
    )
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS return_window_days")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS is_returnable")
