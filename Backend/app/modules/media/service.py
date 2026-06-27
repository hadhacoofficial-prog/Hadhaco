import io
import uuid
from typing import Literal

import boto3
from botocore.config import Config
from PIL import Image

from app.core.config import settings

ImageSize = Literal["original", "thumbnail", "medium", "large"]

_SIZES: dict[ImageSize, tuple[int, int]] = {
    "thumbnail": (200, 200),
    "medium": (600, 600),
    "large": (1200, 1200),
}

_WEBP_QUALITY = 85


def _get_r2_client():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _normalize_image(image: Image.Image) -> Image.Image:
    """
    Return a square RGB image with the source centered on a white canvas.
    Padding is ~12.5% on each side of the longest dimension.
    Never crops or stretches the source image.
    """
    if image.mode in ("RGBA", "P"):
        flat = Image.new("RGB", image.size, (255, 255, 255))
        src = image.convert("RGBA") if image.mode == "P" else image
        flat.paste(src, mask=src.split()[3])
        image = flat
    elif image.mode != "RGB":
        image = image.convert("RGB")

    w, h = image.size
    canvas_size = round(max(w, h) * 1.25)
    canvas = Image.new("RGB", (canvas_size, canvas_size), (255, 255, 255))
    canvas.paste(image, ((canvas_size - w) // 2, (canvas_size - h) // 2))
    return canvas


def _resize_to_webp(image: Image.Image, max_size: tuple[int, int]) -> bytes:
    img = image.copy()
    img.thumbnail(max_size, Image.LANCZOS)  # type: ignore[attr-defined]

    # Convert RGBA → RGB for JPEG-safe WebP output
    if img.mode in ("RGBA", "P"):
        background = Image.new("RGB", img.size, (255, 255, 255))
        if img.mode == "P":
            img = img.convert("RGBA")
        background.paste(img, mask=img.split()[3] if img.mode == "RGBA" else None)
        img = background
    elif img.mode != "RGB":
        img = img.convert("RGB")

    buf = io.BytesIO()
    img.save(buf, format="WEBP", quality=_WEBP_QUALITY, method=4)
    return buf.getvalue()


def _public_url(key: str) -> str:
    base = settings.R2_PUBLIC_URL.rstrip("/")
    return f"{base}/{key}"


def _key_from_url(url: str) -> str:
    """Strip the R2 public base URL to get the bare object key."""
    base = settings.R2_PUBLIC_URL.rstrip("/") + "/"
    return url.removeprefix(base)


class MediaService:
    """
    Centralised image-processing and upload service for Cloudflare R2.

    All upload methods share the same compression pipeline:
    - original (raw bytes as uploaded)
    - thumbnail  200×200 WebP
    - medium     600×600 WebP
    - large     1200×1200 WebP

    Storage layout
    ──────────────
    products/{product_id}/{image_uuid}/original.{ext}
    products/{product_id}/{image_uuid}/thumbnail.webp
    products/{product_id}/{image_uuid}/medium.webp
    products/{product_id}/{image_uuid}/large.webp

    collections/{collection_id}/{image_uuid}/original.{ext}
    collections/{collection_id}/{image_uuid}/thumbnail.webp
    collections/{collection_id}/{image_uuid}/medium.webp
    collections/{collection_id}/{image_uuid}/large.webp

    categories/{category_id}/{image_uuid}/original.{ext}
    …

    Any future entity follows the same pattern via upload_entity_cover().
    """

    # ------------------------------------------------------------------ #
    # Internal helpers
    # ------------------------------------------------------------------ #

    def _upload_image_variants(
        self,
        file_bytes: bytes,
        original_filename: str,
        base_key: str,
    ) -> dict[str, str]:
        """
        Upload original + three WebP sizes under *base_key*.
        Returns dict: original, thumbnail, medium, large → CDN URL.
        """
        client = _get_r2_client()
        bucket = settings.R2_BUCKET_NAME

        ext = (
            original_filename.rsplit(".", 1)[-1].lower()
            if "." in original_filename
            else "jpg"
        )
        original_key = f"{base_key}/original.{ext}"
        client.put_object(
            Bucket=bucket,
            Key=original_key,
            Body=file_bytes,
            ContentType=f"image/{ext}",
        )

        raw = Image.open(io.BytesIO(file_bytes))
        raw.load()
        img: Image.Image = _normalize_image(raw)

        urls: dict[str, str] = {"original": _public_url(original_key)}
        for size_name, max_size in _SIZES.items():
            webp_bytes = _resize_to_webp(img, max_size)
            key = f"{base_key}/{size_name}.webp"
            client.put_object(
                Bucket=bucket,
                Key=key,
                Body=webp_bytes,
                ContentType="image/webp",
            )
            urls[size_name] = _public_url(key)

        return urls

    # ------------------------------------------------------------------ #
    # Public API
    # ------------------------------------------------------------------ #

    def upload_product_image(
        self,
        file_bytes: bytes,
        original_filename: str,
        product_id: uuid.UUID,
    ) -> dict[str, str]:
        """
        Upload original + three WebP sizes for a product.
        Returns dict with keys: original, thumbnail, medium, large (all public CDN URLs).
        """
        image_id = uuid.uuid4()
        base_key = f"products/{product_id}/{image_id}"
        return self._upload_image_variants(file_bytes, original_filename, base_key)

    def upload_entity_cover(
        self,
        file_bytes: bytes,
        original_filename: str,
        entity_type: str,
        entity_id: uuid.UUID,
    ) -> dict[str, str]:
        """
        Upload a cover image for any entity (collections, categories, …).

        Uses the same pipeline as upload_product_image:
          original + thumbnail/medium/large WebP variants.

        Key layout:
          {entity_type}/{entity_id}/{image_uuid}/original.{ext}
          {entity_type}/{entity_id}/{image_uuid}/large.webp
          …

        Returns dict: original, thumbnail, medium, large → CDN URLs.
        The caller should persist urls["large"] as the entity's image_url.
        """
        image_id = uuid.uuid4()
        base_key = f"{entity_type}/{entity_id}/{image_id}"
        return self._upload_image_variants(file_bytes, original_filename, base_key)

    def delete_entity_folder(self, prefix: str) -> None:
        """
        Delete every R2 object whose key starts with *prefix*.

        Use this to purge an entity's image folder before uploading a
        replacement, or when the entity is deleted.

        Example prefixes:
          "collections/{col_id}/{image_uuid}/"   ← one image folder
          "collections/{col_id}/"                ← all images for an entity
        """
        client = _get_r2_client()
        bucket = settings.R2_BUCKET_NAME
        result = client.list_objects_v2(Bucket=bucket, Prefix=prefix)
        if "Contents" in result:
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": o["Key"]} for o in result["Contents"]]},
            )

    def upload_avatar(self, file_bytes: bytes, user_id: str) -> str:
        """Upload a user avatar to R2 as a 400×400 WebP, returning the public URL.

        The key is deterministic (avatars/{user_id}/avatar.webp) so re-uploading
        overwrites the previous avatar with no stale files accumulating.
        """
        img = Image.open(io.BytesIO(file_bytes))
        img.load()
        webp_bytes = _resize_to_webp(img, (400, 400))

        key = f"avatars/{user_id}/avatar.webp"
        _get_r2_client().put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=webp_bytes,
            ContentType="image/webp",
        )
        return _public_url(key)

    def delete_product_image(self, product_id: uuid.UUID, image_id: uuid.UUID) -> None:
        """Delete all size variants for a product image from R2."""
        self.delete_entity_folder(f"products/{product_id}/{image_id}/")

    def upload_bytes(self, content: bytes, *, key: str, content_type: str) -> str:
        """Upload raw bytes to R2 and return the public URL."""
        _get_r2_client().put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=key,
            Body=content,
            ContentType=content_type,
        )
        return _public_url(key)

    def get_presigned_upload_url(
        self, key: str, content_type: str, expires_in: int = 300
    ) -> str:
        """Generate a presigned PUT URL for direct browser-to-R2 uploads."""
        client = _get_r2_client()
        return client.generate_presigned_url(
            "put_object",
            Params={
                "Bucket": settings.R2_BUCKET_NAME,
                "Key": key,
                "ContentType": content_type,
            },
            ExpiresIn=expires_in,
        )

    @staticmethod
    def folder_prefix_from_url(image_url: str) -> str | None:
        """
        Derive the R2 folder prefix from a stored CDN URL.

        e.g. "https://cdn.hadha.co/collections/abc/uuid/large.webp"
             → "collections/abc/uuid/"

        Returns None if the URL doesn't belong to R2_PUBLIC_URL.
        """
        base = settings.R2_PUBLIC_URL.rstrip("/") + "/"
        if not image_url.startswith(base):
            return None
        key = image_url[len(base) :]  # "collections/abc/uuid/large.webp"
        folder = key.rsplit("/", 1)[0] + "/"  # "collections/abc/uuid/"
        return folder
