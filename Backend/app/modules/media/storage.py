"""
Unified R2 storage layer for the Universal Image System — the only place
that talks to Cloudflare R2 for images. One client, one key convention, one
Cache-Control policy.

See docs/architecture/Universal_Responsive_Image_System_Design.md §12.
"""

from __future__ import annotations

import logging
import uuid

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

ORIGINAL_CACHE_CONTROL = "private, max-age=0, must-revalidate"
VARIANT_CACHE_CONTROL = "public, max-age=31536000, immutable"

_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "gif": "image/gif",
}


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def content_type_for_ext(ext: str) -> str:
    return _CONTENT_TYPES.get(ext.lower().lstrip("."), "application/octet-stream")


def build_original_key(
    module: str,
    owner_type: str,
    owner_id: uuid.UUID | None,
    image_id: uuid.UUID,
    ext: str,
) -> str:
    """images/{module}/{owner_type}/{owner_id}/{image_id}/original.{ext}"""
    owner_segment = str(owner_id) if owner_id is not None else "unattached"
    return f"images/{module}/{owner_type}/{owner_segment}/{image_id}/original.{ext.lstrip('.')}"


def build_variant_key(
    module: str,
    owner_type: str,
    owner_id: uuid.UUID | None,
    image_id: uuid.UUID,
    breakpoint: str,
    variant_name: str,
    dpr: int,
    fmt: str,
) -> str:
    """images/{module}/{owner_type}/{owner_id}/{image_id}/{breakpoint}/{variant_name}@{dpr}x.{fmt}"""
    owner_segment = str(owner_id) if owner_id is not None else "unattached"
    return (
        f"images/{module}/{owner_type}/{owner_segment}/{image_id}/"
        f"{breakpoint}/{variant_name}@{dpr}x.{fmt}"
    )


def public_url(key: str, *, version: int | None = None) -> str:
    base = settings.R2_PUBLIC_URL.rstrip("/")
    url = f"{base}/{key}"
    if version is not None:
        url = f"{url}?v={version}"
    return url


def put_original(key: str, content: bytes, *, ext: str) -> None:
    _get_r2_client().put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=content,
        ContentType=content_type_for_ext(ext),
        CacheControl=ORIGINAL_CACHE_CONTROL,
    )


def put_variant(key: str, content: bytes, *, fmt: str) -> None:
    _get_r2_client().put_object(
        Bucket=settings.R2_BUCKET_NAME,
        Key=key,
        Body=content,
        ContentType=content_type_for_ext(fmt),
        CacheControl=VARIANT_CACHE_CONTROL,
    )


def get_object_bytes(key: str) -> bytes:
    obj = _get_r2_client().get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    return obj["Body"].read()


def delete_image_folder(image_id: uuid.UUID, key_prefix: str) -> bool:
    """
    Delete every R2 object under *key_prefix* (an image's full folder,
    e.g. "images/product/product/{product_id}/{image_id}/").

    Returns True on confirmed success, False on failure. Callers (service.py)
    are responsible for the retry/status-tracking policy described in §12 —
    this function never silently swallows an error, it logs and reports.
    """
    client = _get_r2_client()
    bucket = settings.R2_BUCKET_NAME
    try:
        result = client.list_objects_v2(Bucket=bucket, Prefix=key_prefix)
        contents = result.get("Contents", [])
        if not contents:
            return True
        client.delete_objects(
            Bucket=bucket,
            Delete={"Objects": [{"Key": o["Key"]} for o in contents]},
        )
        return True
    except ClientError:
        logger.error(
            "Failed to delete R2 image folder image_id=%s key_prefix=%s",
            image_id,
            key_prefix,
            exc_info=True,
        )
        return False
