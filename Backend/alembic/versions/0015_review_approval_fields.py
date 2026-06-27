"""add review approval tracking and rejection fields

Revision ID: 0015_review_approval_fields
Revises: 0014_complimentary_gift
Create Date: 2026-06-27
"""

import sqlalchemy as sa

from alembic import op

revision = "0015_review_approval_fields"
down_revision = "0014_complimentary_gift"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("reviews", sa.Column("customer_name", sa.VARCHAR(255), nullable=True))
    op.add_column(
        "reviews",
        sa.Column("is_rejected", sa.Boolean(), nullable=False, server_default="false"),
    )
    op.add_column(
        "reviews",
        sa.Column("approved_at", sa.DateTime(timezone=True), nullable=True),
    )
    op.add_column("reviews", sa.Column("approved_by", sa.VARCHAR(255), nullable=True))


def downgrade() -> None:
    op.drop_column("reviews", "approved_by")
    op.drop_column("reviews", "approved_at")
    op.drop_column("reviews", "is_rejected")
    op.drop_column("reviews", "customer_name")
