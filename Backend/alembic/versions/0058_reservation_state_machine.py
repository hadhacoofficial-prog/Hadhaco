"""Reservation state machine: checkout lock + reason-specific terminal states.

Adds three values to inventory_reservation_status:
  - CHECKOUT_IN_PROGRESS: reservation is protected from the short cart-TTL
    expiry sweep while the customer is on the payment gateway (see
    ReservationService.lock_for_checkout).
  - CANCELLED: explicit user/admin cancellation, distinguished from...
  - PAYMENT_FAILED: ...a Razorpay order-create failure, both of which
    previously collapsed into the ambiguous 'RELEASED' value.

Postgres restricts ALTER TYPE ... ADD VALUE from running inside a transaction
block on some versions/usages, so each ADD VALUE runs in its own
autocommit_block (matching the CONCURRENTLY-index precedent in
0054_performance_indexes_phase6.py) rather than relying on alembic's default
per-migration transaction.

Also extends the existing idx_inv_res_user_status_expires partial index
(added in 0057, scoped to status='ACTIVE') with a matching CHECKOUT_IN_PROGRESS
index, since get_user_active_reservations now widens its filter to include
that status.

Revision ID: 0058_reservation_state_machine
Revises: 0057_composite_index_active_reservations
Create Date: 2026-07-24
"""

from alembic import op

revision: str = "0058_reservation_state_machine"
down_revision: str | None = "0057_composite_index_active_reservations"
branch_labels: str | None = None
depends_on: str | None = None


def upgrade() -> None:
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE inventory_reservation_status ADD VALUE IF NOT EXISTS "
            "'CHECKOUT_IN_PROGRESS'"
        )
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE inventory_reservation_status ADD VALUE IF NOT EXISTS "
            "'CANCELLED'"
        )
    with op.get_context().autocommit_block():
        op.execute(
            "ALTER TYPE inventory_reservation_status ADD VALUE IF NOT EXISTS "
            "'PAYMENT_FAILED'"
        )

    # Covers: WHERE user_id = :uid AND status = 'CHECKOUT_IN_PROGRESS' AND expires_at > now()
    op.execute("""
        CREATE INDEX IF NOT EXISTS
        idx_inv_res_user_status_expires_checkout
        ON inventory_reservations (user_id, status, expires_at)
        WHERE status = 'CHECKOUT_IN_PROGRESS'
    """)


def downgrade() -> None:
    # Postgres has no ALTER TYPE ... DROP VALUE — downgrading a live enum
    # requires rewriting the type (create new type, migrate column, drop old,
    # rename) and only makes sense if no row uses the new values.  Since this
    # migration adds capability rather than data, we simply drop the index
    # added above and leave the enum values in place (matches the project's
    # existing precedent — 0005's downgrade doesn't need this since it drops
    # the whole table set, but no other migration in this project drops enum
    # values either).
    op.execute("DROP INDEX IF EXISTS idx_inv_res_user_status_expires_checkout")
