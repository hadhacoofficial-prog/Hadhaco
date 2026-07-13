"""Add rendered_subject and rendered_body to notification_logs.

When a notification first fails and is scheduled for retry, the rendered
(pre-Jinja) content is now stored alongside the log entry.  Retry attempts
use this stored content instead of re-fetching and re-rendering the
template, which prevents two bugs:

1. Template updates between initial send and retry would cause the wrong
   content to be sent to the original recipient.
2. The SMS retry path was sending raw Jinja syntax (template.template_body)
   instead of rendered text, because it skipped the Jinja render step.

Revision ID: 0037_notification_rendered_content
Revises: 0036_feature_flags_table
Create Date: 2026-07-13
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0037_notification_rendered_content"
down_revision: str | None = "0036_feature_flags_table"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None


def upgrade() -> None:
    op.add_column(
        "notification_logs",
        sa.Column("rendered_subject", sa.Text(), nullable=True),
    )
    op.add_column(
        "notification_logs",
        sa.Column("rendered_body", sa.Text(), nullable=True),
    )


def downgrade() -> None:
    op.drop_column("notification_logs", "rendered_body")
    op.drop_column("notification_logs", "rendered_subject")
