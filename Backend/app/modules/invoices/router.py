import uuid

from fastapi import APIRouter, Depends
from fastapi.responses import RedirectResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.database import get_db
from app.core.dependencies import get_current_user, require_customer
from app.modules.invoices.service import InvoiceService
from app.modules.profiles.models import Profile

router = APIRouter()
_service = InvoiceService()


@router.get(
    "/orders/{order_id}/invoice",
    dependencies=[Depends(require_customer)],
)
async def download_invoice(
    order_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    current_user: Profile = Depends(get_current_user),
):
    url = await _service.get_download_url(db, order_id, current_user.id)
    return RedirectResponse(url=url, status_code=302)
