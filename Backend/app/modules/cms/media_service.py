"""CMS Media Service — uploads images/videos to R2 and records in cms_media.

This is the legacy, not-yet-migrated-to-URIS pipeline for hero/banner/CMS
section media (see docs/audits/universal-image-system-production-audit.md
§2). It keeps its own boto3 client and key scheme rather than sharing
app.modules.media.storage — flagged there as an architectural smell (two
image pipelines), but converging it into URIS means giving hero/banner/CMS
a real crop UI first, which is out of scope here. What *is* in scope: the
two gaps this legacy path had relative to URIS — objects served without a
Cache-Control header, and DB-row deletes that never touched R2 — are
fixed below, since those don't require the larger migration."""

from __future__ import annotations

import io
import logging
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError
from fastapi import HTTPException, UploadFile, status
from PIL import Image
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.config import settings
from app.modules.cms.models import CmsMedia
from app.modules.cms.repository import CMSRepository

logger = logging.getLogger(__name__)

_WEBP_QUALITY = 85
_THUMBNAIL_SIZE = (400, 400)

_IMAGE_MIMES = {"image/jpeg", "image/png", "image/webp", "image/gif", "image/avif"}
_VIDEO_MIMES = {"video/mp4", "video/webm", "video/ogg"}
_MAX_FILE_SIZE = 50 * 1024 * 1024  # 50 MB

# CMS objects are stored at a media_id-derived key that's never reused for
# different content (a replace uploads a new id), so — like URIS variants —
# they're safe to cache forever. Previously unset entirely, meaning every
# storefront hero/banner image request revalidated with R2 on every load.
_CACHE_CONTROL = "public, max-age=31536000, immutable"


def _r2():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _public_url(key: str) -> str:
    return f"{settings.R2_PUBLIC_URL.rstrip('/')}/{key}"


def _to_webp(data: bytes, max_size: tuple[int, int]) -> bytes:
    img: Image.Image = Image.open(io.BytesIO(data))
    img.thumbnail(max_size, Image.LANCZOS)  # type: ignore[attr-defined]
    if img.mode in ("RGBA", "P"):
        bg = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        bg.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
        img = bg
    elif img.mode != "RGB":
        img = img.convert("RGB")
    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=_WEBP_QUALITY, method=4)
    return buf.getvalue()


class CmsMediaService:
    def __init__(self) -> None:
        self._repo = CMSRepository()

    async def upload(
        self,
        db: AsyncSession,
        file: UploadFile,
        folder: str,
        alt_text: str | None,
        uploaded_by: uuid.UUID,
    ) -> CmsMedia:
        content_type = file.content_type or "application/octet-stream"
        is_image = content_type in _IMAGE_MIMES
        is_video = content_type in _VIDEO_MIMES

        if not (is_image or is_video):
            raise HTTPException(
                status.HTTP_422_UNPROCESSABLE_ENTITY,
                f"Unsupported file type: {content_type}",
            )

        data = await file.read()
        if len(data) > _MAX_FILE_SIZE:
            raise HTTPException(
                status.HTTP_413_REQUEST_ENTITY_TOO_LARGE, "File exceeds 50 MB limit"
            )

        media_id = uuid.uuid4()
        original_filename = file.filename or "upload"
        safe_folder = folder.strip("/") or "cms"
        ext = (
            original_filename.rsplit(".", 1)[-1].lower()
            if "." in original_filename
            else "bin"
        )
        key = f"{safe_folder}/{media_id}.{ext}"

        client = _r2()
        bucket = settings.R2_BUCKET_NAME

        client.put_object(
            Bucket=bucket,
            Key=key,
            Body=data,
            ContentType=content_type,
            CacheControl=_CACHE_CONTROL,
        )
        cdn_url = _public_url(key)

        width: int | None = None
        height: int | None = None
        thumbnail_url: str | None = None

        if is_image:
            try:
                img = Image.open(io.BytesIO(data))
                width, height = img.size
                thumb_data = _to_webp(data, _THUMBNAIL_SIZE)
                thumb_key = f"{safe_folder}/{media_id}_thumb.webp"
                client.put_object(
                    Bucket=bucket,
                    Key=thumb_key,
                    Body=thumb_data,
                    ContentType="image/webp",
                    CacheControl=_CACHE_CONTROL,
                )
                thumbnail_url = _public_url(thumb_key)
            except (
                Exception
            ):  # noqa: BLE001 — thumbnail is best-effort, upload must still succeed
                logger.warning(
                    "CMS thumbnail generation failed for media %s (%s) — "
                    "continuing without one",
                    media_id,
                    original_filename,
                    exc_info=True,
                )

        media = await self._repo.create_media(
            db,
            id=media_id,
            filename=key,
            original_filename=original_filename,
            mime_type=content_type,
            file_size=len(data),
            width=width,
            height=height,
            cdn_url=cdn_url,
            thumbnail_url=thumbnail_url,
            folder=f"/{safe_folder}",
            alt_text=alt_text,
            uploaded_by=uploaded_by,
        )
        await db.commit()
        await db.refresh(media)
        return media

    def delete_r2_objects(self, media: CmsMedia) -> None:
        """Best-effort R2 cleanup for a `cms_media` row about to be deleted.
        Previously `CMSService.delete_media` only removed the DB row, so
        every CMS delete orphaned its R2 object(s) permanently (no
        soft-delete/lifecycle-rule safety net exists for this legacy path
        the way URIS's `delete_image_folder` provides). Failures are logged,
        not raised — the admin-facing delete must not fail just because R2
        cleanup did; see the identical tradeoff in
        universal_service.UniversalImageService.delete."""
        client = _r2()
        bucket = settings.R2_BUCKET_NAME
        keys = [media.filename]
        if media.thumbnail_url:
            stem, _, ext = media.filename.rpartition(".")
            if stem:
                keys.append(f"{stem}_thumb.webp")
        try:
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": k} for k in keys]},
            )
        except ClientError:
            logger.error(
                "Failed to delete R2 object(s) for cms_media %s: %s",
                media.id,
                keys,
                exc_info=True,
            )
