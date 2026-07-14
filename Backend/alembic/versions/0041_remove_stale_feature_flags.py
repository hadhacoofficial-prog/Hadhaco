"""Remove stale feature flags that were deleted from code but remain in DB.

The following flags were removed from the seed data and codebase but still
exist as rows in the feature_flags table on the live database:

    cart_abandonment_emails
    coupon_one_per_user
    fraud_auto_hold
    low_stock_alerts
    maintenance_mode
    review_gate_verified
    sms_order_confirmation
    sms_shipping_update

Revision ID: 0041
Revises: 0040
Create Date: 2026-07-14
"""

from alembic import op

revision = "0041_remove_stale_feature_flags"
down_revision = "0040_enquiries_user_archived"
branch_labels = None
depends_on = None

STALE_FLAGS = [
    "cart_abandonment_emails",
    "coupon_one_per_user",
    "fraud_auto_hold",
    "low_stock_alerts",
    "maintenance_mode",
    "review_gate_verified",
    "sms_order_confirmation",
    "sms_shipping_update",
]


def upgrade() -> None:
    flags = ", ".join(f"'{f}'" for f in STALE_FLAGS)
    op.execute(f"DELETE FROM feature_flags WHERE key IN ({flags})")


def downgrade() -> None:
    pass
