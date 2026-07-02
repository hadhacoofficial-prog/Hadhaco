"""drop address_line1/address_line2 from company_config

Revision ID: 0018_drop_company_address_lines
Revises: 0017_coupon_rule_engine
Create Date: 2026-07-02
"""

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0018_drop_company_address_lines"
down_revision: str | None = "0017_coupon_rule_engine"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.drop_column("company_config", "address_line1")
    op.drop_column("company_config", "address_line2")


def downgrade() -> None:
    op.add_column(
        "company_config", sa.Column("address_line1", sa.String(255), nullable=True)
    )
    op.add_column(
        "company_config", sa.Column("address_line2", sa.String(255), nullable=True)
    )
