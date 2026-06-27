"""add average_rating and review_count cache to products

Revision ID: 0016_product_rating_cache
Revises: 0015_review_approval_fields
Create Date: 2026-06-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0016_product_rating_cache"
down_revision = "0015_review_approval_fields"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column(
        "products", sa.Column("average_rating", sa.Numeric(3, 1), nullable=True)
    )
    op.add_column(
        "products",
        sa.Column("review_count", sa.Integer(), nullable=False, server_default="0"),
    )


def downgrade() -> None:
    op.drop_column("products", "review_count")
    op.drop_column("products", "average_rating")
