#!/usr/bin/env python
"""
backfill_image_orientation.py — One-time script to fix already-stored
originals that carry a non-default EXIF Orientation tag.

Before universal_service.py's upload()/replace() started calling
_normalize_orientation() (see PATCH .../crop 422 "exceeds source image
bounds" fix), any portrait photo shot with an EXIF rotate-90/180/270 tag was
stored raw: PIL's dimension probe (and original_width/original_height in the
DB) reported the *unrotated* landscape size, while every browser — and the
crop editor, which measures the loaded <img>'s naturalWidth/naturalHeight —
auto-rotates for display and reports the *rotated* portrait size. A crop box
computed against one and validated against the other spuriously fails
strict-bounds validation, or silently clamps to the wrong region on
non-strict presets.

For each affected image this script:
  1. Downloads the stored original from R2.
  2. Bakes in the EXIF orientation (transpose + strip the tag) and re-uploads
     it to the same original_key, overwriting the raw original.
  3. Updates original_width/original_height/original_size_bytes.
  4. Resets every breakpoint's crop to the preset's default centered box —
     any previously-saved crop was computed against the (now provably wrong)
     original dimensions, so it can't be trusted to still make sense.
  5. Regenerates every variant from the corrected original.

Images with no orientation tag are left completely untouched (bytes,
dimensions, crops, variants) — this only touches images the orientation fix
would have applied to at upload time.

Usage (from Backend/):
  python scripts/backfill_image_orientation.py --dry-run   # report only
  python scripts/backfill_image_orientation.py             # apply fixes
  python scripts/backfill_image_orientation.py --force     # ignore progress, redo all

Progress is saved to scripts/backfill_image_orientation_progress.json so the
script can be interrupted and resumed without re-processing already-done
images.

not ran this script yet.

"""

import argparse
import asyncio
import json
import logging
import sys
import uuid
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from sqlalchemy import select

from app.core.database import AsyncSessionLocal
from app.modules.media import storage
from app.modules.media.background import generate_variants_for_breakpoints
from app.modules.media.models import Image
from app.modules.media.preset_registry import get_preset
from app.modules.media.repository import ImageRepository
from app.modules.media.schemas import FocusPointIn
from app.modules.media.universal_service import (
    _default_crops_for_preset,
    _geometry_metadata,
    _normalize_orientation,
    _probe_dimensions,
)

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)-8s %(message)s",
    datefmt="%H:%M:%S",
)
log = logging.getLogger(__name__)

PROGRESS_FILE = Path(__file__).parent / "backfill_image_orientation_progress.json"

_repo = ImageRepository()


def _load_progress() -> dict:
    if PROGRESS_FILE.exists():
        return json.loads(PROGRESS_FILE.read_text())
    return {"done": [], "corrected": [], "failed": []}


def _save_progress(progress: dict) -> None:
    PROGRESS_FILE.write_text(json.dumps(progress, indent=2))


async def _get_candidate_image_ids() -> list[str]:
    async with AsyncSessionLocal() as db:
        result = await db.execute(
            select(Image.id).where(
                Image.deleted_at.is_(None),
                Image.mime_type != "image/svg+xml",
            )
        )
        return [str(i) for i in result.scalars().all()]


async def _process_one(image_id: str, *, dry_run: bool) -> bool:
    """Returns True if the image needed (or, in --dry-run, would need) a fix."""
    async with AsyncSessionLocal() as db:
        image = await _repo.get_image(db, uuid.UUID(image_id))
        if image is None:
            return False

        original_bytes = await storage.get_object_bytes(image.original_key)
        normalized_bytes = _normalize_orientation(original_bytes)
        if normalized_bytes == original_bytes:
            return False

        width, height = _probe_dimensions(normalized_bytes)
        log.info(
            "  image %s: %sx%s -> %sx%s (orientation baked in)",
            image_id,
            image.original_width,
            image.original_height,
            width,
            height,
        )
        if dry_run:
            return True

        await storage.put_original(
            image.original_key, normalized_bytes, ext=image.original_ext
        )

        preset = get_preset(image.preset_id)
        focus_point = FocusPointIn()
        crops = _default_crops_for_preset(preset, width or 1, height or 1)
        image = await _repo.update_fields(
            db,
            image,
            {
                "original_width": width,
                "original_height": height,
                "original_size_bytes": len(normalized_bytes),
                "version": image.version + 1,
                "metadata_": _geometry_metadata(
                    preset, width, height, crops, focus_point
                ),
            },
        )
        await _repo.delete_all_variants(db, image)

        await generate_variants_for_breakpoints(
            db, image, preset, normalized_bytes, crops, preset.breakpoints
        )
        return True


async def main(*, dry_run: bool, force: bool) -> None:
    progress = (
        {"done": [], "corrected": [], "failed": []} if force else _load_progress()
    )
    done_set: set[str] = set(progress.get("done", []))
    corrected_list: list[str] = progress.get("corrected", [])
    failed_list: list[dict] = progress.get("failed", [])

    log.info("Fetching candidate images from DB…")
    image_ids = await _get_candidate_image_ids()
    log.info(f"Found {len(image_ids)} raster images, {len(done_set)} already checked.")

    todo = [i for i in image_ids if i not in done_set]

    for idx, image_id in enumerate(todo, 1):
        log.info(f"[{idx}/{len(todo)}] image {image_id}")
        try:
            corrected = await _process_one(image_id, dry_run=dry_run)
            if corrected:
                corrected_list.append(image_id)
            if not dry_run:
                done_set.add(image_id)
                _save_progress(
                    {
                        "done": list(done_set),
                        "corrected": corrected_list,
                        "failed": failed_list,
                    }
                )
        except Exception as exc:
            log.error(f"  FAILED: {exc}")
            failed_list.append({"id": image_id, "error": str(exc)})
            if not dry_run:
                _save_progress(
                    {
                        "done": list(done_set),
                        "corrected": corrected_list,
                        "failed": failed_list,
                    }
                )

    log.info("=" * 60)
    log.info(f"Checked   : {len(todo)}")
    log.info(f"Corrected : {len(corrected_list)}")
    log.info(f"Failed    : {len(failed_list)}")
    if failed_list:
        log.warning("Failed image IDs:")
        for f in failed_list:
            log.warning(f"  {f['id']}  {f['error']}")


if __name__ == "__main__":
    parser = argparse.ArgumentParser(
        description="Backfill EXIF-orientation normalization for existing images"
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Report which images would be corrected without changing anything",
    )
    parser.add_argument(
        "--force", action="store_true", help="Ignore progress file and redo all images"
    )
    args = parser.parse_args()
    asyncio.run(main(dry_run=args.dry_run, force=args.force))
