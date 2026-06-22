from fastapi import APIRouter, Depends, Header, HTTPException, Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import ok
from app.core.database import get_db
from app.middleware.rate_limit import rate_limit_webhook
from app.modules.webhooks.service import WebhookService

router = APIRouter()
_service = WebhookService()


@router.post(
    "/webhooks/razorpay",
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
    result = await _service.handle_razorpay(db, body, x_razorpay_signature)
    if result.get("status") == "invalid_signature":
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    return ok(result, ResponseCode.WEBHOOK_PROCESSED, "Webhook processed successfully")


@router.post(
    "/webhooks/delivery-one",
    include_in_schema=False,
    dependencies=[Depends(rate_limit_webhook)],
)
async def delivery_one_webhook(
    request: Request,
    x_delivery_signature: str | None = Header(None, alias="X-Delivery-Signature"),
    db: AsyncSession = Depends(get_db),
):
    if not x_delivery_signature:
        raise HTTPException(status_code=400, detail="Missing signature header")
    body = await request.body()
    result = await _service.handle_delivery_one(db, body, x_delivery_signature)
    if result.get("status") == "invalid_signature":
        raise HTTPException(status_code=401, detail="Invalid webhook signature")
    return ok(result, ResponseCode.WEBHOOK_PROCESSED, "Webhook processed successfully")
