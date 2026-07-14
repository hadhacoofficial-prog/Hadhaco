"""Create contact_enquiries table for the Contact Us form.

Stores enquiries submitted via the storefront Contact Us page.
Admin-only management with status workflow:
  new_enquiry → contacted_customer → positive_response → negative_response → closed

Revision ID: 0039_contact_enquiries
Revises: 0038_trigram_indexes_orders_profiles
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects.postgresql import UUID

revision: str = "0039_contact_enquiries"
down_revision: str | None = "0038_trigram_indexes_orders_profiles"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.create_table(
        "contact_enquiries",
        sa.Column("id", UUID(as_uuid=True), primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("name", sa.String(255), nullable=False),
        sa.Column("email", sa.String(255), nullable=False),
        sa.Column("phone", sa.String(50), nullable=True),
        sa.Column("subject", sa.String(500), nullable=False),
        sa.Column("message", sa.Text(), nullable=False),
        sa.Column(
            "status",
            sa.String(30),
            nullable=False,
            server_default="new_enquiry",
        ),
        sa.Column("admin_notes", sa.Text(), nullable=True),
        sa.Column("contacted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.CheckConstraint(
            "status IN ('new_enquiry','contacted_customer','positive_response','negative_response','closed')",
            name="contact_enquiries_status_check",
        ),
    )

    op.create_index("idx_contact_enquiries_status", "contact_enquiries", ["status"])
    op.create_index("idx_contact_enquiries_created", "contact_enquiries", ["created_at"])
    op.create_index("idx_contact_enquiries_email", "contact_enquiries", ["email"])


def downgrade() -> None:
    op.drop_index("idx_contact_enquiries_email", table_name="contact_enquiries")
    op.drop_index("idx_contact_enquiries_created", table_name="contact_enquiries")
    op.drop_index("idx_contact_enquiries_status", table_name="contact_enquiries")
    op.drop_table("contact_enquiries")
