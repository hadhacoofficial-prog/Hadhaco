import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.redis import get_redis
from app.modules.catalog.repository import ProductRepository
from app.modules.catalog.router import _bust_product_list_cache
from app.modules.catalog.schemas import ProductImageResponse
from app.modules.categories.repository import CategoryRepository
from app.modules.collections.repository import CollectionRepository
from app.modules.media.service import MediaService

router = APIRouter()
_media = MediaService()
_product_repo = ProductRepository()
_collection_repo = CollectionRepository()
_category_repo = CategoryRepository()

_ALLOWED_TYPES = {"image/jpeg", "image/png", "image/webp"}
_MAX_SIZE = 10 * 1024 * 1024  # 10 MB


class ImageUploadResponse(BaseModel):
    url: str


class ImageCropRequest(BaseModel):
    """
    Crop box in pixel coordinates of the untouched original image, as
    produced by react-easy-crop's onCropComplete(croppedAreaPixels).
    """

    crop_x: float = Field(ge=0)
    crop_y: float = Field(ge=0)
    crop_width: float = Field(gt=0)
    crop_height: float = Field(gt=0)
    crop_zoom: float = Field(default=1.0, gt=0)
    crop_rotation: float = Field(default=0.0)


def _validate_image(file: UploadFile, file_bytes: bytes) -> None:
    if file.content_type not in _ALLOWED_TYPES:
        raise HTTPException(
            status_code=422, detail=f"Unsupported image type: {file.content_type}"
        )
    if len(file_bytes) > _MAX_SIZE:
        raise HTTPException(status_code=413, detail="Image exceeds 10 MB limit")


# ─────────────────────────────────────────────────────────────
# Product images
# ─────────────────────────────────────────────────────────────


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
    redis: aioredis.Redis = Depends(get_redis),
):
    from app.common.responses import created

    product = await _product_repo.get_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")

    file_bytes = await file.read()
    _validate_image(file, file_bytes)

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
            "large_url": urls.get("large"),
            "alt_text": None,
            "is_primary": is_primary,
            "sort_order": 0,
        },
    )

    if is_primary:
        await _product_repo.set_primary_image(db, product_id, img.id)

    await _bust_product_list_cache(redis)
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
    redis: aioredis.Redis = Depends(get_redis),
):
    result = await _product_repo.delete_image(db, image_id)
    if not result:
        raise HTTPException(status_code=404, detail="Image not found")
    try:
        _media.delete_product_image(product_id, image_id)
    except Exception:
        pass
    await _bust_product_list_cache(redis)
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
    redis: aioredis.Redis = Depends(get_redis),
):
    product = await _product_repo.get_by_id(db, product_id)
    if not product:
        raise HTTPException(status_code=404, detail="Product not found")
    await _product_repo.set_primary_image(db, product_id, image_id)
    await _bust_product_list_cache(redis)
    return ok(None, ResponseCode.MEDIA_PRIMARY_SET, "Primary image set successfully")


@router.patch(
    "/admin/products/{product_id}/images/{image_id}/crop",
    response_model=BaseSuccessResponse[ProductImageResponse],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def crop_product_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    payload: ImageCropRequest,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Regenerate thumbnail/medium/large from a crop of the ORIGINAL image.
    original.{ext} is never touched, so re-editing the crop later always
    starts from the same untouched source.
    """
    img = await _product_repo.get_image(db, image_id)
    if not img or img.product_id != product_id:
        raise HTTPException(status_code=404, detail="Image not found")

    urls = _media.apply_crop_to_product_image(
        img.url,
        payload.crop_x,
        payload.crop_y,
        payload.crop_width,
        payload.crop_height,
        payload.crop_rotation,
    )

    updated = await _product_repo.update_image(
        db,
        image_id,
        {
            "thumbnail_url": urls.get("thumbnail"),
            "medium_url": urls.get("medium"),
            "large_url": urls.get("large"),
            "crop_x": payload.crop_x,
            "crop_y": payload.crop_y,
            "crop_width": payload.crop_width,
            "crop_height": payload.crop_height,
            "crop_zoom": payload.crop_zoom,
            "crop_rotation": payload.crop_rotation,
        },
    )
    await _bust_product_list_cache(redis)
    return ok(
        ProductImageResponse.model_validate(updated),
        ResponseCode.MEDIA_IMAGE_CROPPED,
        "Image cropped successfully",
    )


@router.put(
    "/admin/products/{product_id}/images/{image_id}/replace",
    response_model=BaseSuccessResponse[ProductImageResponse],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def replace_product_image(
    product_id: uuid.UUID,
    image_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    """
    Replace an image's original file in place (same image_id, same URL
    layout). Any previously saved crop is discarded — the new original has
    no crop applied yet, so the caller should open the crop editor again.
    """
    img = await _product_repo.get_image(db, image_id)
    if not img or img.product_id != product_id:
        raise HTTPException(status_code=404, detail="Image not found")

    file_bytes = await file.read()
    _validate_image(file, file_bytes)

    urls = _media.replace_product_image(
        file_bytes, file.filename or "upload.jpg", product_id, image_id
    )

    updated = await _product_repo.update_image(
        db,
        image_id,
        {
            "url": urls["original"],
            "thumbnail_url": urls.get("thumbnail"),
            "medium_url": urls.get("medium"),
            "large_url": urls.get("large"),
            "crop_x": None,
            "crop_y": None,
            "crop_width": None,
            "crop_height": None,
            "crop_zoom": None,
            "crop_rotation": None,
        },
    )
    await _bust_product_list_cache(redis)
    return ok(
        ProductImageResponse.model_validate(updated),
        ResponseCode.MEDIA_IMAGE_REPLACED,
        "Image replaced successfully",
    )


# ─────────────────────────────────────────────────────────────
# Collection images
# ─────────────────────────────────────────────────────────────


@router.post(
    "/admin/collections/{col_id}/image",
    response_model=BaseSuccessResponse[ImageUploadResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def upload_collection_image(
    col_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    from app.common.responses import created

    collection = await _collection_repo.get_by_id(db, col_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    file_bytes = await file.read()
    _validate_image(file, file_bytes)

    # Delete previous image folder from R2 before uploading replacement
    if collection.image_url:
        old_prefix = MediaService.folder_prefix_from_url(collection.image_url)
        if old_prefix:
            try:
                _media.delete_entity_folder(old_prefix)
            except Exception:
                pass

    urls = _media.upload_entity_cover(
        file_bytes,
        file.filename or "upload.jpg",
        "collections",
        col_id,
    )

    # Persist the CDN-optimised large WebP URL
    await _collection_repo.update(db, col_id, {"image_url": urls["large"]})

    return created(
        ImageUploadResponse(url=urls["large"]),
        ResponseCode.MEDIA_IMAGE_UPLOADED,
        "Collection image uploaded",
    )


@router.delete(
    "/admin/collections/{col_id}/image",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_collection_image(
    col_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    collection = await _collection_repo.get_by_id(db, col_id)
    if not collection:
        raise HTTPException(status_code=404, detail="Collection not found")

    if collection.image_url:
        old_prefix = MediaService.folder_prefix_from_url(collection.image_url)
        if old_prefix:
            try:
                _media.delete_entity_folder(old_prefix)
            except Exception:
                pass
        await _collection_repo.update(db, col_id, {"image_url": None})

    return deleted(ResponseCode.MEDIA_IMAGE_DELETED, "Collection image deleted")


# ─────────────────────────────────────────────────────────────
# Category images
# ─────────────────────────────────────────────────────────────


@router.post(
    "/admin/categories/{cat_id}/image",
    response_model=BaseSuccessResponse[ImageUploadResponse],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def upload_category_image(
    cat_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    from app.common.responses import created

    category = await _category_repo.get_by_id(db, cat_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    file_bytes = await file.read()
    _validate_image(file, file_bytes)

    # Delete previous image folder from R2 before uploading replacement
    if category.image_url:
        old_prefix = MediaService.folder_prefix_from_url(category.image_url)
        if old_prefix:
            try:
                _media.delete_entity_folder(old_prefix)
            except Exception:
                pass

    urls = _media.upload_entity_cover(
        file_bytes,
        file.filename or "upload.jpg",
        "categories",
        cat_id,
    )

    # Persist the CDN-optimised large WebP URL
    await _category_repo.update(db, cat_id, {"image_url": urls["large"]})

    return created(
        ImageUploadResponse(url=urls["large"]),
        ResponseCode.MEDIA_IMAGE_UPLOADED,
        "Category image uploaded",
    )


@router.delete(
    "/admin/categories/{cat_id}/image",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_category_image(
    cat_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    category = await _category_repo.get_by_id(db, cat_id)
    if not category:
        raise HTTPException(status_code=404, detail="Category not found")

    if category.image_url:
        old_prefix = MediaService.folder_prefix_from_url(category.image_url)
        if old_prefix:
            try:
                _media.delete_entity_folder(old_prefix)
            except Exception:
                pass
        await _category_repo.update(db, cat_id, {"image_url": None})

    return deleted(ResponseCode.MEDIA_IMAGE_DELETED, "Category image deleted")
