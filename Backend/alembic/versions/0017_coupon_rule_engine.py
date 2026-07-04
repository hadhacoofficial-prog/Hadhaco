"""production-grade coupon rule engine — extend coupons table

Revision ID: 0017_coupon_rule_engine
Revises: 0016_product_rating_cache
Create Date: 2026-06-27
"""

import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

from alembic import op

revision = "0017_coupon_rule_engine"
down_revision = "0016_product_rating_cache"
branch_labels = None
depends_on = None


def upgrade() -> None:
    # Status replaces the boolean is_active (draft/inactive/active).
    # Default to 'active' so existing rows behave identically.
    op.add_column(
        "coupons",
        sa.Column(
            "status",
            sa.String(10),
            nullable=False,
            server_default="active",
        ),
    )
    # Migrate is_active → status for existing rows
    op.execute(
        "UPDATE coupons SET status = CASE WHEN is_active THEN 'active' ELSE 'inactive' END"
    )

    # Customer eligibility rules
    op.add_column(
        "coupons",
        sa.Column(
            "first_order_only", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "coupons",
        sa.Column(
            "new_customer_only", sa.Boolean(), nullable=False, server_default="false"
        ),
    )
    op.add_column(
        "coupons",
        sa.Column(
            "returning_customer_only",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.add_column(
        "coupons",
        sa.Column(
            "one_time_per_customer",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )

    # Order value constraints
    op.add_column(
        "coupons",
        sa.Column("max_order_amount", sa.Numeric(12, 2), nullable=True),
    )

    # Product / category restrictions (arrays stored as JSONB)
    op.add_column(
        "coupons",
        sa.Column("eligible_product_ids", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "coupons",
        sa.Column("eligible_collection_ids", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "coupons",
        sa.Column("eligible_category_slugs", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "coupons",
        sa.Column("excluded_product_ids", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "coupons",
        sa.Column("excluded_category_slugs", postgresql.JSONB(), nullable=True),
    )

    # Audience restrictions
    op.add_column(
        "coupons",
        sa.Column("allowed_emails", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "coupons",
        sa.Column("allowed_phone_numbers", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "coupons",
        sa.Column("customer_groups", postgresql.JSONB(), nullable=True),
    )

    # Region restrictions
    op.add_column(
        "coupons",
        sa.Column("allowed_states", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "coupons",
        sa.Column("allowed_cities", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "coupons",
        sa.Column("allowed_pincodes", postgresql.JSONB(), nullable=True),
    )

    # Payment / shipping method restrictions
    op.add_column(
        "coupons",
        sa.Column("allowed_payment_methods", postgresql.JSONB(), nullable=True),
    )
    op.add_column(
        "coupons",
        sa.Column("allowed_shipping_methods", postgresql.JSONB(), nullable=True),
    )

    # Stacking and campaign grouping
    op.add_column(
        "coupons",
        sa.Column("stackable", sa.Boolean(), nullable=False, server_default="true"),
    )
    op.add_column(
        "coupons",
        sa.Column("campaign_name", sa.String(100), nullable=True),
    )

    # Index on status for fast filtering
    op.create_index("idx_coupons_status", "coupons", ["status"])
    op.create_index("idx_coupons_campaign", "coupons", ["campaign_name"])


def downgrade() -> None:
    # Reconcile the legacy is_active boolean against status before dropping
    # it, so coupons set to 'draft' or 'inactive' after this migration was
    # applied don't silently revert to active on rollback.
    op.execute("UPDATE coupons SET is_active = (status = 'active')")

    op.drop_index("idx_coupons_campaign", table_name="coupons")
    op.drop_index("idx_coupons_status", table_name="coupons")

    for col in [
        "campaign_name",
        "stackable",
        "allowed_shipping_methods",
        "allowed_payment_methods",
        "allowed_pincodes",
        "allowed_cities",
        "allowed_states",
        "customer_groups",
        "allowed_phone_numbers",
        "allowed_emails",
        "excluded_category_slugs",
        "excluded_product_ids",
        "eligible_category_slugs",
        "eligible_collection_ids",
        "eligible_product_ids",
        "max_order_amount",
        "one_time_per_customer",
        "returning_customer_only",
        "new_customer_only",
        "first_order_only",
        "status",
    ]:
        op.drop_column("coupons", col)
