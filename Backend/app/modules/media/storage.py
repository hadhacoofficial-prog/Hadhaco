"""
Unified R2 storage layer for the Universal Image System — the only place
that talks to Cloudflare R2 for images. One client, one key convention, one
Cache-Control policy.

See docs/architecture/Universal_Responsive_Image_System_Design.md §12.
"""

from __future__ import annotations

import asyncio
import logging
import uuid
from collections.abc import Callable
from functools import lru_cache

import boto3
from botocore.config import Config
from botocore.exceptions import ClientError

from app.core.config import settings

logger = logging.getLogger(__name__)

ORIGINAL_CACHE_CONTROL = "private, max-age=0, must-revalidate"
VARIANT_CACHE_CONTROL = "public, max-age=31536000, immutable"

# Variant generation runs synchronously in-request (see universal_service.py
# module docstring for why) and every put/get is offloaded via
# asyncio.to_thread onto the process-wide default ThreadPoolExecutor
# (min(32, cpu+4) workers, shared with every other blocking call in the
# app). A handful of concurrent large-preset uploads (product = 18 R2 calls
# each) can fill that pool and stall unrelated request I/O that also uses
# to_thread. This semaphore caps how many R2 calls THIS module will run at
# once — it doesn't fix the synchronous-in-request architecture (that needs
# a real task queue, tracked as a follow-up), but it puts a hard ceiling on
# the blast radius of a burst of uploads instead of letting them exhaust
# the shared pool. Docs audit CB-1.
_R2_CONCURRENCY = asyncio.Semaphore(8)


async def _run_bounded[T](fn: Callable[[], T]) -> T:
    async with _R2_CONCURRENCY:
        return await asyncio.to_thread(fn)


_CONTENT_TYPES = {
    "jpg": "image/jpeg",
    "jpeg": "image/jpeg",
    "png": "image/png",
    "webp": "image/webp",
    "svg": "image/svg+xml",
    "gif": "image/gif",
}


@lru_cache(maxsize=1)
def _get_r2_client():
    # boto3 clients are thread-safe and cheap to reuse — cached so every
    # storage call below doesn't pay TLS/credential-resolution setup cost
    # on top of the thread-offloaded network round-trip.
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


async def put_original(key: str, content: bytes, *, ext: str) -> None:
    def _put() -> None:
        _get_r2_client().put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=content,
            ContentType=content_type_for_ext(ext),
            CacheControl=ORIGINAL_CACHE_CONTROL,
        )

    await _run_bounded(_put)


async def put_variant(key: str, content: bytes, *, fmt: str) -> None:
    def _put() -> None:
        _get_r2_client().put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=content,
            ContentType=content_type_for_ext(fmt),
            CacheControl=VARIANT_CACHE_CONTROL,
        )

    await _run_bounded(_put)


async def get_object_bytes(key: str) -> bytes:
    def _get() -> bytes:
        obj = _get_r2_client().get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
        return obj["Body"].read()

    return await _run_bounded(_get)


async def delete_image_folder(image_id: uuid.UUID, key_prefix: str) -> bool:
    """
    Delete every R2 object under *key_prefix* (an image's full folder,
    e.g. "images/product/product/{product_id}/{image_id}/").

    Returns True on confirmed success, False on failure. Callers (service.py)
    are responsible for the retry/status-tracking policy described in §12 —
    this function never silently swallows an error, it logs and reports.
    """
    bucket = settings.R2_BUCKET_NAME

    def _delete() -> bool:
        client = _get_r2_client()
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

    return await _run_bounded(_delete)
