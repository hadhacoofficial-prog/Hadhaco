from __future__ import annotations

from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.modules.notifications.models import NotificationTemplate
from app.modules.notifications.providers.registry import registry


class NotificationDispatcher:
    """Single entry point business logic goes through to actually send.

    Resolves the concrete provider via the ProviderRegistry — NotificationService
    never imports ResendProvider/WhatsAppProvider directly.
    """

    async def send_email(
        self, db: AsyncSession, *, to: str, subject: str, html: str
    ) -> str:
        provider = registry.get_email_provider()
        return await provider.send_email(db, to=to, subject=subject, html=html)

    async def send_whatsapp_template(
        self,
        db: AsyncSession,
        *,
        to: str,
        template: NotificationTemplate,
        context: dict[str, Any],
    ) -> str:
        variables = template.variables or {}
        template_name = variables.get("whatsapp_template", template.name)
        language = variables.get("whatsapp_lang", "en_US")
        params: list[str] = variables.get("params", [])

        components: list[dict] = []
        if params:
            components.append(
                {
                    "type": "body",
                    "parameters": [
                        {"type": "text", "text": str(context.get(p, ""))}
                        for p in params
                    ],
                }
            )

        provider = registry.get_whatsapp_provider()
        return await provider.send_whatsapp(
            db,
            to=to,
            template_name=template_name,
            language=language,
            components=components,
        )


dispatcher = NotificationDispatcher()
