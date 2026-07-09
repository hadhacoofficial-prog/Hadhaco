import uuid

import redis.asyncio as aioredis
from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.core.redis import bust_product_list_cache, get_redis
from app.modules.media.crop_engine import CropGeometryError
from app.modules.media.repository import ImageRepository
from app.modules.media.schemas import (
    AltTextIn,
    AttachIn,
    CropGeometryIn,
    ImageOut,
    OwnerType,
    PresetOut,
    ReorderIn,
)
from app.modules.media.universal_service import (
    UniversalImageService,
    UniversalImageServiceError,
)
from app.modules.media.validation import ImageValidationError

router = APIRouter()
_universal = UniversalImageService()
_image_repo = ImageRepository()


# ─────────────────────────────────────────────────────────────
# Universal Image System — the single upload/crop/replace/attach/
# reorder/delete/regenerate surface for every image module
# (product, collection, category, hero, banner, avatar, review,
# etc.). See docs/architecture/Universal_Responsive_Image_System_Design.md.
# ─────────────────────────────────────────────────────────────


async def _get_image_or_404(db: AsyncSession, image_id: uuid.UUID):
    image = await _image_repo.get_image(db, image_id)
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    return image


async def _bust_cache_for(owner_type: OwnerType, redis: aioredis.Redis) -> None:
    """Product images feed the storefront's cached product list/cards
    (`ProductListItem.primary_image`), which nothing in the media module
    otherwise invalidates — a crop/replace/set-primary/upload/delete here
    used to leave that cache serving a stale thumbnail for up to
    `_PRODUCT_LIST_TTL` seconds after the edit."""
    if owner_type == "product":
        await bust_product_list_cache(redis)


@router.get(
    "/admin/media/presets",
    response_model=BaseSuccessResponse[list[PresetOut]],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def list_presets():
    presets = [PresetOut.from_preset(p) for p in _universal.list_presets()]
    return ok(
        presets, ResponseCode.UNIVERSAL_PRESETS_LISTED, "Presets listed successfully"
    )


@router.get(
    "/admin/media/{image_id}",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def get_universal_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
):
    """Fetch one image's full state — original_url, crop metadata, and
    variants. The crop editor's "Edit Crop" flow calls this to always
    re-open against the untouched original plus the previously-saved crop
    geometry, rather than trusting whatever variant URL happens to be
    cached in the caller's local UI state."""
    image = await _get_image_or_404(db, image_id)
    return ok(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_IMAGE_FETCHED,
        "Image fetched successfully",
    )


@router.post(
    "/admin/media/{preset_id}/upload",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=201,
)
async def upload_universal_image(
    preset_id: str,
    file: UploadFile = File(...),
    owner_type: OwnerType = "unattached",
    owner_id: uuid.UUID | None = None,
    # Set by callers (the crop editor's upload-then-crop flow) that will
    # immediately follow this upload with a PATCH .../crop carrying the
    # real geometry — skips generating-then-discarding a default-centered
    # variant set for every fresh upload (docs audit HP-5).
    skip_initial_generation: bool = False,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
    admin=Depends(require_admin),
):
    from app.common.responses import created

    file_bytes = await file.read()
    try:
        image = await _universal.upload(
            db,
            preset_id=preset_id,
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            owner_type=owner_type,
            owner_id=owner_id,
            uploaded_by=admin.id,
            skip_initial_generation=skip_initial_generation,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UniversalImageServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    await _bust_cache_for(owner_type, redis)
    return created(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_IMAGE_UPLOADED,
        "Image uploaded successfully",
    )


@router.patch(
    "/admin/media/{image_id}/crop",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def crop_universal_image(
    image_id: uuid.UUID,
    payload: CropGeometryIn,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    image = await _get_image_or_404(db, image_id)
    owner_type = image.owner_type
    try:
        image = await _universal.crop(db, image=image, payload=payload)
    except (
        CropGeometryError,
        ImageValidationError,
        UniversalImageServiceError,
    ) as exc:
        # Only genuine "this crop request is invalid" cases map to 422 — a
        # real outage (R2 down, DB error, unexpected exception) must not be
        # reported to the admin as a validation error, or an on-call
        # engineer has no signal that anything actually broke (docs audit
        # HP-3). Anything else propagates and gets the app's normal 500
        # handling/alerting.
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _bust_cache_for(owner_type, redis)
    return ok(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_IMAGE_CROPPED,
        "Crop saved successfully",
    )


@router.put(
    "/admin/media/{image_id}/replace",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def replace_universal_image(
    image_id: uuid.UUID,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    image = await _get_image_or_404(db, image_id)
    owner_type = image.owner_type
    file_bytes = await file.read()
    try:
        image = await _universal.replace(
            db,
            image=image,
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
        )
    except UniversalImageServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _bust_cache_for(owner_type, redis)
    return ok(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_IMAGE_REPLACED,
        "Image replaced successfully",
    )


@router.patch(
    "/admin/media/{image_id}/attach",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def attach_universal_image(
    image_id: uuid.UUID,
    payload: AttachIn,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    image = await _get_image_or_404(db, image_id)
    image = await _universal.attach(
        db, image=image, owner_type=payload.owner_type, owner_id=payload.owner_id
    )
    await _bust_cache_for(payload.owner_type, redis)
    return ok(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_IMAGE_ATTACHED,
        "Image attached successfully",
    )


@router.patch(
    "/admin/media/{image_id}/alt-text",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def update_universal_image_alt_text(
    image_id: uuid.UUID,
    payload: AltTextIn,
    db: AsyncSession = Depends(get_db),
):
    image = await _get_image_or_404(db, image_id)
    image = await _universal.update_alt_text(db, image=image, alt_text=payload.alt_text)
    return ok(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_ALT_TEXT_UPDATED,
        "Alt text updated successfully",
    )


@router.patch(
    "/admin/media/reorder",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def reorder_universal_images(
    payload: ReorderIn,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    await _universal.reorder(
        db, [(item.image_id, item.sort_order) for item in payload.items]
    )
    await _bust_cache_for(payload.owner_type, redis)
    return ok(
        None, ResponseCode.UNIVERSAL_IMAGES_REORDERED, "Images reordered successfully"
    )


@router.patch(
    "/admin/media/{image_id}/set-primary",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def set_primary_universal_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    image = await _get_image_or_404(db, image_id)
    owner_type = image.owner_type
    try:
        image = await _universal.set_primary(db, image=image)
    except UniversalImageServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    await _bust_cache_for(owner_type, redis)
    return ok(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_IMAGE_SET_PRIMARY,
        "Primary image set successfully",
    )


@router.delete(
    "/admin/media/{image_id}",
    response_model=BaseSuccessResponse[None],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def delete_universal_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    image = await _get_image_or_404(db, image_id)
    owner_type = image.owner_type
    await _universal.delete(db, image=image)
    await _bust_cache_for(owner_type, redis)
    return deleted(ResponseCode.UNIVERSAL_IMAGE_DELETED, "Image deleted successfully")


@router.post(
    "/admin/media/{image_id}/regenerate",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def regenerate_universal_image(
    image_id: uuid.UUID,
    db: AsyncSession = Depends(get_db),
    redis: aioredis.Redis = Depends(get_redis),
):
    image = await _get_image_or_404(db, image_id)
    owner_type = image.owner_type
    image = await _universal.regenerate(db, image=image)
    await _bust_cache_for(owner_type, redis)
    return ok(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_VARIANTS_REGENERATED,
        "Variants regenerated successfully",
    )
