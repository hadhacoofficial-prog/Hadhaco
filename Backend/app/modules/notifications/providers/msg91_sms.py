from __future__ import annotations

import re

import httpx
import structlog

from app.core.config import settings
from app.modules.notifications.providers.base import NotificationProvider

logger = structlog.get_logger(__name__)

_API_URL = "https://api.msg91.com/api/v5/flow/"


def _normalize_mobile(phone: str) -> str:
    """
    Strip whitespace/dashes/+ and ensure a leading country code is present.
    Indian numbers without country code get 91 prepended.
    Example: +91-98765-43210 → 919876543210
    """
    digits = re.sub(r"[^\d]", "", phone)
    if len(digits) == 10:
        digits = "91" + digits
    return digits


class MSG91SMSProvider(NotificationProvider):
    """
    MSG91 v5 Flow API provider.

    The MSG91 flow template on their dashboard must contain a variable named
    ``##message##`` that will receive the fully-rendered notification body.
    """

    async def send_email(self, *, to: str, subject: str, html: str) -> str:
        raise NotImplementedError("MSG91 does not support email")

    async def send_sms(self, *, to: str, body: str) -> str:
        mobile = _normalize_mobile(to)
        payload = {
            "flow_id": settings.MSG91_TEMPLATE_ID,
            "sender": settings.MSG91_SENDER_ID,
            "mobiles": mobile,
            "message": body,
        }
        log = logger.bind(provider="msg91", mobile=mobile)

        async with httpx.AsyncClient() as client:
            resp = await client.post(
                _API_URL,
                headers={
                    "authkey": settings.MSG91_API_KEY,
                    "Content-Type": "application/json",
                    "Accept": "application/json",
                },
                json=payload,
                timeout=10,
            )

        try:
            resp.raise_for_status()
        except httpx.HTTPStatusError as exc:
            log.error(
                "msg91_http_error",
                status_code=exc.response.status_code,
                response_body=exc.response.text,
            )
            raise

        data: dict = resp.json()

        if data.get("type") != "success":
            log.error("msg91_api_error", response=data)
            raise RuntimeError(
                f"MSG91 rejected the request: {data.get('message', data)}"
            )

        request_id: str = data.get("request_id", "")
        log.info("sms_sent", request_id=request_id)
        return request_id
