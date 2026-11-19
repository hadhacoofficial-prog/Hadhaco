"""Per-product return policy wording: ``products.return_policy_label``.

Optional customer-facing text shown on the product page in place of the
generated "N-day returns" / "No return, no refund" line. ``{days}`` in the text
is replaced with the product's return window. NULL means use the generated
wording, so every existing product is unchanged.

Additive and re-runnable (IF NOT EXISTS). A nullable column with no default is
metadata-only on PostgreSQL, so there is no table rewrite. lock_timeout makes
the step fail fast instead of queueing storefront reads behind it; the deploy
retries migrations. No existing row is modified.

Revision ID: 0072_product_return_policy_label
Revises: 0071_product_return_policy
Create Date: 2026-11-19
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0072_product_return_policy_label"
down_revision: str | None = "0071_product_return_policy"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute(
        "ALTER TABLE products ADD COLUMN IF NOT EXISTS "
        "return_policy_label VARCHAR(100)"
    )


def downgrade() -> None:
    op.execute("SET LOCAL lock_timeout = '5s'")
    op.execute("ALTER TABLE products DROP COLUMN IF EXISTS return_policy_label")
