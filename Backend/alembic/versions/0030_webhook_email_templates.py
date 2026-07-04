"""Add notification_templates rows needed by the Razorpay webhook handlers:
payment_failed_email (optional customer-facing failure notice) and
refund_failed_admin_alert (sent to ADMIN_ALERT_EMAIL, since a failed refund
needs human follow-up with Razorpay or the customer).

Data-only migration — notification_templates itself is created in
supabase/sql/012_notifications.sql; this just inserts two rows, matching
the style of supabase/sql/023_seed_data.sql's existing template inserts.
ON CONFLICT (name) DO NOTHING keeps it safe to re-run.

Revision ID: 0030_webhook_email_templates
Revises: 0029_webhook_events_expansion
Create Date: 2026-07-03
"""

from __future__ import annotations

from collections.abc import Sequence

import sqlalchemy as sa

from alembic import op

revision: str = "0030_webhook_email_templates"
down_revision: str | None = "0029_webhook_events_expansion"
branch_labels: str | Sequence[str] | None = None
depends_on: str | Sequence[str] | None = None

_PAYMENT_FAILED_BODY = (
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;'
    'font-family:Helvetica,Arial,sans-serif;"><table role="presentation" '
    'width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" '
    'style="padding:24px 12px;"><table role="presentation" width="100%" '
    'style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;">'
    '<tr><td style="background:#1c1b1a;padding:20px 32px;text-align:center;">'
    '<span style="color:#e8e2d9;font-size:22px;letter-spacing:3px;">HADHA.CO</span>'
    '</td></tr><tr><td style="padding:32px;"><h2 style="margin:0 0 12px;'
    'color:#1c1b1a;">We could not process your payment</h2>'
    '<p style="color:#555;line-height:1.6;">Your payment for order '
    "<strong>{{order_number}}</strong> could not be completed"
    "{% if reason %} ({{reason}}){% endif %}. Your cart items have been "
    "released back to stock — please try again or use a different payment "
    'method.</p><p style="text-align:center;margin:28px 0;">'
    '<a href="https://hadha.co/cart" style="background:#1c1b1a;color:#fff;'
    "text-decoration:none;padding:12px 28px;border-radius:4px;"
    'display:inline-block;">Try Again</a></p></td></tr>'
    '<tr><td style="padding:16px 32px;background:#f0ede8;color:#999;'
    'font-size:12px;text-align:center;">© Hadha.co · Hallmarked 925 Silver'
    "</td></tr></table></td></tr></table></body></html>"
)

_REFUND_FAILED_ADMIN_BODY = (
    '<!DOCTYPE html><html><body style="margin:0;padding:0;background:#f7f5f2;'
    'font-family:Helvetica,Arial,sans-serif;"><table role="presentation" '
    'width="100%" cellpadding="0" cellspacing="0"><tr><td align="center" '
    'style="padding:24px 12px;"><table role="presentation" width="100%" '
    'style="max-width:600px;background:#ffffff;border-radius:8px;overflow:hidden;">'
    '<tr><td style="background:#8a1c1c;padding:16px 32px;text-align:center;">'
    '<span style="color:#fff;font-size:18px;letter-spacing:2px;">'
    'HADHA ADMIN ALERT</span></td></tr><tr><td style="padding:32px;">'
    '<h2 style="margin:0 0 12px;color:#1c1b1a;">Refund failed</h2>'
    '<p style="color:#555;line-height:1.6;">Refund <strong>{{refund_id}}</strong> '
    "of <strong>₹{{amount}}</strong> for order <strong>{{order_number}}</strong> "
    "failed at Razorpay: <strong>{{reason}}</strong>. This needs manual "
    "follow-up with Razorpay support or the customer.</p></td></tr></table>"
    "</td></tr></table></body></html>"
)


def upgrade() -> None:
    stmt = sa.text(
        "INSERT INTO notification_templates "
        "(name, channel, event_type, subject, template_body, is_active) VALUES "
        "(:name, :channel, :event_type, :subject, :body, TRUE) "
        "ON CONFLICT (name) DO NOTHING"
    )
    op.get_bind().execute(
        stmt,
        {
            "name": "payment_failed_email",
            "channel": "email",
            "event_type": "payment_failed",
            "subject": "We could not process your payment for order {{order_number}}",
            "body": _PAYMENT_FAILED_BODY,
        },
    )
    op.get_bind().execute(
        stmt,
        {
            "name": "refund_failed_admin_alert",
            "channel": "email",
            "event_type": "refund_failed_admin_alert",
            "subject": "[Hadha Admin] Refund failed for order {{order_number}}",
            "body": _REFUND_FAILED_ADMIN_BODY,
        },
    )


def downgrade() -> None:
    op.execute(
        "DELETE FROM notification_templates "
        "WHERE name IN ('payment_failed_email', 'refund_failed_admin_alert')"
    )
