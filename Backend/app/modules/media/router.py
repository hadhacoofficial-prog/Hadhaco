import uuid

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.modules.catalog.repository import ProductRepository
from app.modules.catalog.schemas import ProductImageResponse
from app.modules.media.service import MediaService

router = APIRouter()
_media = MediaService()
_product_repo = ProductRepository()

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


@router.post(
    "/admin/products/{product_id}/images",
    response_model=BaseSuccessResponse[ProductImageResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def upload_product_image(
    product_id: uuid.UUID,
    file: UploadFile = File(...),
    is_primary: bool = False,
    db: AsyncSession = Depends(get_db),
):
    from app.common.responses import created

    product = await _product_repo.get_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=422, detail=f"Unsupported image type: {file.content_type}"
        )

    file_bytes = await file.read()
    if len(file_bytes) > _MAX_SIZE:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit")

    urls = _media.upload_product_image(
        file_bytes, file.filename or "upload.jpg", product_id
    )

    img = await _product_repo.add_image(
        db,
        {
            "id": uuid.uuid4(),
            "product_id": product_id,
            "url": urls["original"],
            "thumbnail_url": urls.get("thumbnail"),
            "medium_url": urls.get("medium"),
            "alt_text": None,
            "is_primary": is_primary,
            "sort_order": 0,
        },
    )

    if is_primary:
        await _product_repo.set_primary_image(db, product_id, img.id)

    return created(
        ProductImageResponse.model_validate(img),
        ResponseCode.MEDIA_IMAGE_UPLOADED,
        "Image uploaded successfully",
    )


@router.delete(
    "/admin/products/{product_id}/images/{image_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_product_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    result = await _product_repo.delete_image(db, image_id)
    if not result:
        raise HTTPException(status_code=404, detail="Image not found")
    # Best-effort R2 deletion (don't fail if R2 is unavailable)
    try:
        _media.delete_product_image(product_id, image_id)
    except Exception:
        pass
    return deleted(ResponseCode.MEDIA_IMAGE_DELETED, "Image deleted successfully")


@router.patch(
    "/admin/products/{product_id}/images/{image_id}/primary",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def set_primary_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    product = await _product_repo.get_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await _product_repo.set_primary_image(db, product_id, image_id)
    return ok(None, ResponseCode.MEDIA_PRIMARY_SET, "Primary image set successfully")
