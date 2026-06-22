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


def _resize_to_webp(image: Image.Image, max_size: tuple[int, int]) -> bytes:
    img = image.copy()
    img.thumbnail(max_size, Image.LANCZOS)

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


class MediaService:
    """
    Handles image uploads to Cloudflare R2.
    Produces thumbnail (200×200), medium (600×600), large (1200×1200) WebP variants
    plus stores the original.
    """

    def upload_product_image(
        self,
        file_bytes: bytes,
        original_filename: str,
        product_id: uuid.UUID,
    ) -> dict[str, str]:
        """
        Upload original + three WebP sizes.
        Returns dict with keys: original, thumbnail, medium, large (all public CDN URLs).
        """
        client = _get_r2_client()
        bucket = settings.R2_BUCKET_NAME

        image_id = uuid.uuid4()
        base_key = f"products/{product_id}/{image_id}"

        # Upload original
        ext = original_filename.rsplit(".", 1)[-1].lower() if "." in original_filename else "jpg"
        original_key = f"{base_key}/original.{ext}"
        client.put_object(
            Bucket=bucket,
            Key=original_key,
            Body=file_bytes,
            ContentType=f"image/{ext}",
        )

        # Open with Pillow for resizing
        img = Image.open(io.BytesIO(file_bytes))
        img.load()

        urls: dict[str, str] = {
            "original": _public_url(original_key),
        }

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
        """Delete all size variants for an image from R2."""
        client = _get_r2_client()
        bucket = settings.R2_BUCKET_NAME
        base_key = f"products/{product_id}/{image_id}"

        objects = client.list_objects_v2(Bucket=bucket, Prefix=base_key + "/")
        if "Contents" in objects:
            client.delete_objects(
                Bucket=bucket,
                Delete={"Objects": [{"Key": o["Key"]} for o in objects["Contents"]]},
            )

    def get_presigned_upload_url(self, key: str, content_type: str, expires_in: int = 300) -> str:
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
