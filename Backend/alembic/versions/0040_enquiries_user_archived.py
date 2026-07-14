"""Add user_id FK and is_archived flag to contact_enquiries.

user_id links enquiries to authenticated customers (nullable for guests).
is_archived enables soft-delete without removing records.

Revision ID: 0040_enquiries_user_archived
Revises: 0039_contact_enquiries
Create Date: 2026-07-14
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa
from sqlalchemy.dialects.postgresql import UUID

from alembic import op

revision: str = "0040_enquiries_user_archived"
down_revision: str | None = "0039_contact_enquiries"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "contact_enquiries",
        sa.Column(
            "user_id",
            UUID(as_uuid=True),
            sa.ForeignKey("profiles.id", ondelete="SET NULL"),
            nullable=True,
        ),
    )
    op.add_column(
        "contact_enquiries",
        sa.Column(
            "is_archived",
            sa.Boolean(),
            nullable=False,
            server_default="false",
        ),
    )
    op.create_index(
        "idx_contact_enquiries_user_id",
        "contact_enquiries",
        ["user_id"],
    )


def downgrade() -> None:
    op.drop_index("idx_contact_enquiries_user_id", table_name="contact_enquiries")
    op.drop_column("contact_enquiries", "is_archived")
    op.drop_column("contact_enquiries", "user_id")
