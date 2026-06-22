from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import PlainTextResponse
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.modules.seo.service import SeoService

router = APIRouter()
_service = SeoService()


class SeoPageUpsertRequest(BaseModel):
    path: str
    title: str | None = None
    description: str | None = None
    canonical_url: str | None = None
    og_image: str | None = None
    og_title: str | None = None
    og_description: str | None = None
    structured_data: str | None = None
    noindex: bool = False


class SeoRedirectRequest(BaseModel):
    from_path: str
    to_path: str
    status_code: int = 301


@router.get("/seo/page", response_model=BaseSuccessResponse[dict])
async def get_seo_page(path: str, db: AsyncSession = Depends(get_db)):
    data = await _service.get_page(db, path)
    if not data:
        raise HTTPException(status_code=404, detail="SEO page not found")
    return ok(data, ResponseCode.SEO_PAGE_FETCHED, "SEO page fetched successfully")


@router.put(
    "/admin/seo/pages",
    response_model=BaseSuccessResponse[dict],
    dependencies=[Depends(require_admin)],
)
async def upsert_seo_page(
    payload: SeoPageUpsertRequest,
    db: AsyncSession = Depends(get_db),
):
    result = await _service.upsert_page(db, payload.model_dump())
    return ok(result, ResponseCode.SEO_PAGE_UPSERTED, "SEO page upserted successfully")


@router.post(
    "/admin/seo/redirects",
    response_model=BaseSuccessResponse[None],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def create_redirect(
    payload: SeoRedirectRequest,
    db: AsyncSession = Depends(get_db),
):
    from app.common.responses import created

    await _service.create_redirect(
        db, payload.from_path, payload.to_path, payload.status_code
    )
    return created(
        None, ResponseCode.SEO_REDIRECT_CREATED, "Redirect created successfully"
    )


@router.get("/sitemap.xml", response_class=PlainTextResponse)
async def sitemap(db: AsyncSession = Depends(get_db)):
    xml = await _service.generate_sitemap(db)
    return PlainTextResponse(content=xml, media_type="application/xml")
