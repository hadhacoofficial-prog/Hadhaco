from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import ok
from app.core.database import get_db
from app.middleware.rate_limit import rate_limit_webhook
from app.modules.webhooks.service import WebhookService

router = APIRouter()
_service = WebhookService()

# Headers worth keeping on the webhook_events row for debugging delivery
# issues — never the full header set (avoids storing anything sensitive
# beyond what's needed to diagnose a bad delivery).
_AUDITED_HEADERS = (
    "x-razorpay-signature",
    "x-razorpay-event-id",
    "content-type",
    "user-agent",
)


@router.post(
    "/payments/webhook/razorpay",
    include_in_schema=False,
    dependencies=[Depends(rate_limit_webhook)],
)
async def razorpay_webhook(
    request: Request,
    x_razorpay_signature: str | None = Header(None, alias="X-Razorpay-Signature"),
    db: AsyncSession = Depends(get_db),
):
    if not x_razorpay_signature:
        raise HTTPException(status_code=400, detail="Missing signature header")
    body = await request.body()
    audited_headers = {
        h: request.headers[h] for h in _AUDITED_HEADERS if h in request.headers
    }
    result = await _service.handle_razorpay(
        db, body, x_razorpay_signature, headers=audited_headers
    )
    if result.get("status") == "invalid_signature":
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    if result.get("status") == "processing_failed":
        # Non-2xx so Razorpay's retry mechanism re-delivers this event
        # instead of treating a failed handler as successfully processed.
        raise HTTPException(status_code=500, detail="Webhook processing failed")
    return ok(result, ResponseCode.WEBHOOK_PROCESSED, "Webhook processed successfully")
