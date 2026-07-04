"""Add a real FK from coupon_usages.order_id to orders.id (schema audit
C8/H6). The column already participates in a UniqueConstraint(coupon_id,
order_id) but had zero FK enforcement, leaving it an unconstrained
reference to financial reconciliation data.

Added NOT VALID (enforced for new/updated rows immediately, existing
rows are not scanned or locked at migration time) since coupon_usages
is populated via a two-step write (order_id starts NULL, filled in once
the order is created) and any legacy orphaned values haven't been
audited. ON DELETE SET NULL matches the column's existing nullable,
audit-trail-style semantics rather than blocking order deletion.

Revision ID: 0024_coupon_usages_order_fk
Revises: 0023_fk_ondelete_fixes
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0024_coupon_usages_order_fk"
down_revision: str | None = "0023_fk_ondelete_fixes"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE coupon_usages ADD CONSTRAINT coupon_usages_order_id_fkey "
        "FOREIGN KEY (order_id) REFERENCES orders(id) ON DELETE SET NULL NOT VALID"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE coupon_usages DROP CONSTRAINT IF EXISTS coupon_usages_order_id_fkey"
    )
