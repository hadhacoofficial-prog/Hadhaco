"""Transactional auth emails (verify address, reset password).

Sent straight through the Resend provider with templates built from the shared
email components. They deliberately bypass the admin-editable
``notification_templates`` table and its enable/disable switches: an admin
turning a template off must never be able to lock customers out of signing up
or recovering an account.
"""

from __future__ import annotations

from urllib.parse import quote

import structlog
from jinja2.sandbox import SandboxedEnvironment

from app.core.config import settings
from app.modules.notifications.branding import get_brand_context
from app.modules.notifications.dispatcher import dispatcher
from app.modules.notifications.dto import EmailPayload
from app.modules.notifications.emails import components as c

log = structlog.get_logger(__name__)

_jinja = SandboxedEnvironment(autoescape=True)


def _page(
    *, title: str, preheader: str, hero_title: str, subtitle: str, cta: str
) -> str:
    return c.document(
        title=title,
        preheader=preheader,
        body_html=c.header()
        + c.hero(
            badge_text="Account",
            badge_bg=c.GOLD,
            title=hero_title,
            subtitle=subtitle,
        )
        + c.cta_block((cta, "{{ action_url }}"))
        + c.paragraph(
            "If the button does not work, copy this link into your browser:<br>"
            '<span style="word-break:break-all;">{{ action_url }}</span>'
        )
        + c.info_note("{{ footnote }}")
        + c.spacer(30)
        + c.footer(),
    )


_VERIFY_HTML = _page(
    title="Verify your email — {{ brand_name }}",
    preheader="Confirm your email address to activate your account.",
    hero_title="Confirm your email{% if full_name %}, {{ full_name }}{% endif %}",
    subtitle=(
        "Thanks for creating a {{ brand_name }} account. Confirm your email "
        "address to finish signing up."
    ),
    cta="Verify Email",
)

_RESET_HTML = _page(
    title="Reset your password — {{ brand_name }}",
    preheader="Use this link to choose a new password.",
    hero_title="Reset your password",
    subtitle=(
        "We received a request to reset the password on your {{ brand_name }} "
        "account. Choose a new one with the button below."
    ),
    cta="Reset Password",
)


def build_action_url(surface: str, path: str, token: str) -> str:
    """Link into the storefront or admin app carrying the one-time token."""
    base = (settings.ADMIN_URL if surface == "admin" else settings.FRONTEND_URL).rstrip(
        "/"
    )
    return f"{base}{path}?token={quote(token, safe='')}"


async def _send(*, to: str, subject: str, template: str, context: dict) -> None:
    html = _jinja.from_string(template).render(**{**get_brand_context(), **context})
    payload = EmailPayload(
        to=to,
        subject=subject,
        html=html,
        api_key=settings.RESEND_API_KEY,
        from_name=settings.EMAIL_FROM_NAME,
        from_email=settings.EMAIL_FROM,
        reply_to=settings.EMAIL_REPLY_TO,
    )
    await dispatcher.send_email(payload)


async def send_verification_email(
    *, to: str, full_name: str | None, action_url: str
) -> None:
    """Never raises: a mail outage must not fail registration (the user can
    request a new link)."""
    try:
        await _send(
            to=to,
            subject="Verify your email address",
            template=_VERIFY_HTML,
            context={
                "full_name": full_name or "",
                "action_url": action_url,
                "footnote": (
                    f"This link expires in {settings.AUTH_VERIFY_TTL_HOURS} hours. "
                    "If you did not create an account, you can ignore this email."
                ),
            },
        )
    except Exception:
        log.warning("auth_verification_email_failed", exc_info=True)


async def send_password_reset_email(*, to: str, action_url: str) -> None:
    try:
        await _send(
            to=to,
            subject="Reset your password",
            template=_RESET_HTML,
            context={
                "action_url": action_url,
                "footnote": (
                    f"This link expires in {settings.AUTH_RESET_TTL_MINUTES} minutes "
                    "and can be used once. If you did not ask for a reset, ignore "
                    "this email — your password has not changed."
                ),
            },
        )
    except Exception:
        log.warning("auth_reset_email_failed", exc_info=True)
