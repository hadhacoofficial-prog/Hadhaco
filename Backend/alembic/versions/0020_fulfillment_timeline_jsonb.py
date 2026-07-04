"""Convert fulfillment_timeline.details from JSON to JSONB.

Aligns the column with every other JSON-typed column in the codebase
(coupons' restriction columns, CMS config/snapshot, support attachments,
analytics/fraud metadata all use JSONB), making it indexable and usable
in containment queries.

Revision ID: 0020_fulfillment_timeline_jsonb
Revises: 0019_per_template_logos
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

from alembic import op

revision: str = "0020_fulfillment_timeline_jsonb"
down_revision: str | None = "0019_per_template_logos"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.execute(
        "ALTER TABLE fulfillment_timeline "
        "ALTER COLUMN details TYPE JSONB USING details::text::jsonb"
    )


def downgrade() -> None:
    op.execute(
        "ALTER TABLE fulfillment_timeline "
        "ALTER COLUMN details TYPE JSON USING details::text::json"
    )
