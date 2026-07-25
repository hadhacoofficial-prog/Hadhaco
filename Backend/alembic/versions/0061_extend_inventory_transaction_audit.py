"""Extend inventory_transactions with a full admin audit trail.

InventoryTransaction previously had no way to say *who* made a change, *why*,
or correlate it back to the HTTP request that triggered it — only a free-form
``reference`` string. This adds the columns the new admin inventory UI's
audit trail (and its Add/Remove/Set adjustment dialog) needs:

  - performed_by:      the admin user (nullable — many transactions are
                        system-driven: checkout completion, expiry sweep,
                        returns processed by a worker, not a human).
  - request_id:         correlation id from the request_id middleware, for
                        tracing a stock change back to the exact request.
  - adjustment_mode:    'ADD' | 'REMOVE' | 'SET', populated only for
                        transaction_type='ADJUSTMENT' rows, so the UI can
                        render "Set to 12" distinctly from "+5"/"-3" using
                        the same signed `quantity` column.
  - reason / notes:     structured reason code + free-text elaboration,
                        required by the admin adjustment dialog going
                        forward (enforced at the Pydantic schema layer, not
                        the DB — existing rows have neither).

Also adds idx_inv_txn_variant_id, which was missing despite variant_id
existing on this table since its original migration — needed for the new
admin inventory page's per-variant "expand row" history query.

Revision ID: 0061_extend_inventory_transaction_audit
Revises: 0060_backfill_default_variants
Create Date: 2026-07-25
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0061_extend_inventory_transaction_audit"
down_revision: str | None = "0060_backfill_default_variants"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute("""
        ALTER TABLE inventory_transactions
            ADD COLUMN IF NOT EXISTS performed_by UUID NULL
                REFERENCES profiles(id) ON DELETE SET NULL,
            ADD COLUMN IF NOT EXISTS request_id VARCHAR(64) NULL,
            ADD COLUMN IF NOT EXISTS adjustment_mode VARCHAR(10) NULL,
            ADD COLUMN IF NOT EXISTS reason VARCHAR(100) NULL,
            ADD COLUMN IF NOT EXISTS notes TEXT NULL
    """)
    op.execute(
        "CREATE INDEX IF NOT EXISTS idx_inv_txn_variant_id "
        "ON inventory_transactions (variant_id)"
    )


def downgrade() -> None:
    op.execute("DROP INDEX IF EXISTS idx_inv_txn_variant_id")
    op.execute("""
        ALTER TABLE inventory_transactions
            DROP COLUMN IF EXISTS notes,
            DROP COLUMN IF EXISTS reason,
            DROP COLUMN IF EXISTS adjustment_mode,
            DROP COLUMN IF EXISTS request_id,
            DROP COLUMN IF EXISTS performed_by
    """)
