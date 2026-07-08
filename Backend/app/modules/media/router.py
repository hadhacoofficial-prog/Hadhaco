import uuid

from fastapi import APIRouter, BackgroundTasks, Depends, File, HTTPException, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from app.common.response_codes import ResponseCode
from app.common.responses import BaseSuccessResponse, deleted, ok
from app.core.database import get_db
from app.core.dependencies import require_admin
from app.modules.media.repository import ImageRepository
from app.modules.media.schemas import (
    AttachIn,
    CropGeometryIn,
    ImageOut,
    PresetOut,
    ReorderIn,
)
from app.modules.media.universal_service import (
    UniversalImageService,
    UniversalImageServiceError,
)

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


@router.post(
    "/admin/media/{preset_id}/upload",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=201,
    dependencies=[Depends(require_admin)],
)
async def upload_universal_image(
    preset_id: str,
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    owner_type: str = "unattached",
    owner_id: uuid.UUID | None = None,
    db: AsyncSession = Depends(get_db),
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
            uploaded_by=None,
            background_tasks=background_tasks,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except UniversalImageServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

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
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    image = await _get_image_or_404(db, image_id)
    try:
        image = await _universal.crop(
            db, image=image, payload=payload, background_tasks=background_tasks
        )
    except (
        Exception
    ) as exc:  # noqa: BLE001 — CropGeometryError or similar surfaces as 422
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
    background_tasks: BackgroundTasks,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    image = await _get_image_or_404(db, image_id)
    file_bytes = await file.read()
    try:
        image = await _universal.replace(
            db,
            image=image,
            file_bytes=file_bytes,
            filename=file.filename or "upload",
            content_type=file.content_type or "application/octet-stream",
            background_tasks=background_tasks,
        )
    except UniversalImageServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
):
    image = await _get_image_or_404(db, image_id)
    image = await _universal.attach(
        db, image=image, owner_type=payload.owner_type, owner_id=payload.owner_id
    )
    return ok(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_IMAGE_ATTACHED,
        "Image attached successfully",
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
):
    await _universal.reorder(
        db, [(item.image_id, item.sort_order) for item in payload.items]
    )
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
):
    image = await _get_image_or_404(db, image_id)
    try:
        image = await _universal.set_primary(db, image=image)
    except UniversalImageServiceError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
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
):
    image = await _get_image_or_404(db, image_id)
    await _universal.delete(db, image=image)
    return deleted(ResponseCode.UNIVERSAL_IMAGE_DELETED, "Image deleted successfully")


@router.post(
    "/admin/media/{image_id}/regenerate",
    response_model=BaseSuccessResponse[ImageOut],
    status_code=200,
    dependencies=[Depends(require_admin)],
)
async def regenerate_universal_image(
    image_id: uuid.UUID,
    background_tasks: BackgroundTasks,
    db: AsyncSession = Depends(get_db),
):
    image = await _get_image_or_404(db, image_id)
    image = await _universal.regenerate(
        db, image=image, background_tasks=background_tasks
    )
    return ok(
        ImageOut.from_image(image),
        ResponseCode.UNIVERSAL_VARIANTS_REGENERATED,
        "Variant regeneration started",
    )
