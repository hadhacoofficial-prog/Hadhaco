#!/usr/bin/env python
"""
migrate_images.py — One-time script to re-normalize all existing product images.

For each product image already in the DB:
  1. Fetch the original bytes from R2.
  2. Normalize (square canvas, white bg, ~12.5% padding per side).
  3. Regenerate thumbnail, medium, large WebP variants.
  4. Re-upload to R2 (overwrites the three variant files; original is untouched).

Usage (from Backend/):
  python scripts/migrate_images.py
  python scripts/migrate_images.py --force   # ignore progress and redo all

Progress is saved to scripts/migrate_progress.json so the script can be
interrupted and resumed without re-processing already-done images.
"""

import argparse
import asyncio
import io
import json
import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

import boto3
from app.modules.media.service import _SIZES, _normalize_image, _resize_to_webp
from botocore.config import Config
from PIL import Image
from sqlalchemy import text

from app.core.config import settings
from app.core.database import AsyncWorkerSessionLocal

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PROGRESS_FILE = Path(__file__).parent / "migrate_progress.json"


def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"done": [], "failed": []}


def _save_progress(progress: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


def _get_r2():
    return boto3.client(
        "s3",
        endpoint_url=settings.R2_ENDPOINT_URL,
        aws_access_key_id=settings.R2_ACCESS_KEY_ID,
        aws_secret_access_key=settings.R2_SECRET_ACCESS_KEY,
        config=Config(signature_version="s3v4"),
        region_name="auto",
    )


def _key_from_url(url: str) -> str:
    base = settings.R2_PUBLIC_URL.rstrip("/") + "/"
    return url.removeprefix(base)


async def _get_all_images() -> list[dict]:
    async with AsyncWorkerSessionLocal() as db:
        result = await db.execute(
            text(
                "SELECT id::text, url, product_id::text "
                "FROM product_images "
                "ORDER BY product_id, sort_order"
            )
        )
        return [{"id": r.id, "url": r.url, "product_id": r.product_id} for r in result]


def _migrate_one(r2, url: str) -> None:
    """Download original, normalize, regenerate and re-upload three variant sizes."""
    key = _key_from_url(url)

    # base_key is the directory: products/{pid}/{iid}
    # key looks like: products/{pid}/{iid}/original.jpg
    base_key = key.rsplit("/", 1)[0]

    resp = r2.get_object(Bucket=settings.R2_BUCKET_NAME, Key=key)
    file_bytes = resp["Body"].read()

    img = Image.open(io.BytesIO(file_bytes))
    img.load()
    img = _normalize_image(img)

    for size_name, max_size in _SIZES.items():
        webp_bytes = _resize_to_webp(img, max_size)
        variant_key = f"{base_key}/{size_name}.webp"
        r2.put_object(
            Bucket=settings.R2_BUCKET_NAME,
            Key=variant_key,
            Body=webp_bytes,
            ContentType="image/webp",
        )


async def main(force: bool) -> None:
    progress = {} if force else _load_progress()
    done_set: set[str] = set(progress.get("done", []))
    failed_list: list[dict] = progress.get("failed", [])

    log.info("Fetching all product images from DB…")
    images = await _get_all_images()
    log.info(f"Found {len(images)} total, {len(done_set)} already migrated.")

    r2 = _get_r2()
    todo = [img for img in images if img["id"] not in done_set]

    for idx, img in enumerate(todo, 1):
        log.info(f"[{idx}/{len(todo)}] image {img['id']}  product {img['product_id']}")
        try:
            _migrate_one(r2, img["url"])
            done_set.add(img["id"])
            _save_progress({"done": list(done_set), "failed": failed_list})
            log.info("  done")
        except Exception as exc:
            log.error(f"  FAILED: {exc}")
            failed_list.append({"id": img["id"], "url": img["url"], "error": str(exc)})
            _save_progress({"done": list(done_set), "failed": failed_list})

    log.info("=" * 60)
    log.info(f"Migrated : {len(done_set)}")
    log.info(f"Failed   : {len(failed_list)}")
    if failed_list:
        log.warning("Failed image IDs:")
        for f in failed_list:
            log.warning(f"  {f['id']}  {f['error']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Re-normalize existing product image variants"
    )
    parser.add_argument(
        "--force", action="store_true", help="Ignore progress file and redo all images"
    )
    args = parser.parse_args()
    asyncio.run(main(args.force))
