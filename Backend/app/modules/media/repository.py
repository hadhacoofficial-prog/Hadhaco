from __future__ import annotations

import uuid
from datetime import UTC, datetime, timedelta
from typing import Any

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.media.models import Image, ImageVariant


class ImageRepository:
    async def create_image(self, db: AsyncSession, **kwargs: Any) -> Image:
        image = Image(**kwargs)
        db.add(image)
        await db.flush()
        await db.refresh(image)
        await db.refresh(image, attribute_names=["variants"])
        return image

    async def get_image(self, db: AsyncSession, image_id: uuid.UUID) -> Image | None:
        result = await db.execute(
            select(Image)
            .options(selectinload(Image.variants))
            .where(Image.id == image_id, Image.deleted_at.is_(None))
        )
        return result.scalar_one_or_none()

    async def list_for_owner(
        self, db: AsyncSession, owner_type: str, owner_id: uuid.UUID
    ) -> list[Image]:
        result = await db.execute(
            select(Image)
            .options(selectinload(Image.variants))
            .where(
                Image.owner_type == owner_type,
                Image.owner_id == owner_id,
                Image.deleted_at.is_(None),
            )
            .order_by(Image.sort_order)
        )
        return list(result.scalars().all())

    async def update_metadata(
        self, db: AsyncSession, image: Image, metadata: dict[str, Any]
    ) -> Image:
        image.metadata_ = metadata
        image.version += 1
        db.add(image)
        await db.flush()
        await db.refresh(image)
        await db.refresh(image, attribute_names=["variants"])
        return image

    async def update_fields(
        self, db: AsyncSession, image: Image, data: dict[str, Any]
    ) -> Image:
        for k, v in data.items():
            setattr(image, k, v)
        db.add(image)
        await db.flush()
        await db.refresh(image)
        await db.refresh(image, attribute_names=["variants"])
        return image

    # ── Background generation queue (CB-1 Phase 2) ──────────────────────
    #
    # `image.status` doubles as the job state ("pending" = queued,
    # "processing" = a worker has claimed it, "ready"/"failed" = done).
    # Per-attempt bookkeeping (attempts/last_error/timestamps) lives in
    # `metadata_["generation"]` rather than new columns — it's diagnostic
    # data, not something any query needs to filter/join on, so a JSONB
    # blob avoids a migration for this pass.

    async def try_claim_pending(
        self, db: AsyncSession, image_id: uuid.UUID
    ) -> Image | None:
        """
        Atomically transitions one image from 'pending' to 'processing' via
        an UPDATE ... WHERE status='pending' ... RETURNING — whichever
        caller (the in-request fast-path task, or the periodic recovery
        poller) gets here first wins the claim; the other sees 0 rows
        updated and gets None back. This is what makes it safe for both
        paths to race on the same image without double-generating it.
        Returns the claimed image (variants loaded) or None if it wasn't
        claimable (already claimed/finished, soft-deleted, or gone).
        """
        result = await db.execute(
            update(Image)
            .where(
                Image.id == image_id,
                Image.status == "pending",
                Image.deleted_at.is_(None),
            )
            .values(status="processing", updated_at=func.now())
            .returning(Image.id)
        )
        claimed_id = result.scalar_one_or_none()
        await db.flush()
        if claimed_id is None:
            return None

        image = await self.get_image(db, claimed_id)
        if image is None:
            return None
        generation = dict(image.metadata_.get("generation", {}) or {})
        generation["attempts"] = generation.get("attempts", 0) + 1
        generation["started_at"] = datetime.now(UTC).isoformat()
        image.metadata_ = {**image.metadata_, "generation": generation}
        db.add(image)
        await db.flush()
        await db.refresh(image)
        return image

    async def reclaim_stale_processing(
        self, db: AsyncSession, *, stale_after_seconds: int
    ) -> int:
        """
        Resets images stuck in 'processing' longer than
        *stale_after_seconds* back to 'pending' so the next poll picks them
        up again — recovers from a worker process crashing (or being
        redeployed) mid-generation, since an `asyncio.create_task` fast-path
        run has no durability of its own. `updated_at` is the staleness
        clock; explicitly bumped on claim above since Core-style `update()`
        statements bypass the ORM's `onupdate=func.now()`.
        """
        cutoff = datetime.now(UTC) - timedelta(seconds=stale_after_seconds)
        result = await db.execute(
            update(Image)
            .where(Image.status == "processing", Image.updated_at < cutoff)
            .values(status="pending", updated_at=func.now())
            .returning(Image.id)
        )
        ids = result.scalars().all()
        await db.flush()
        return len(ids)

    async def list_pending_images(self, db: AsyncSession, *, limit: int) -> list[Image]:
        """Images awaiting generation, oldest-queued first — the periodic
        worker's batch source. Each is still individually claimed via
        `try_claim_pending` before processing, so a concurrent fast-path
        task claiming the same image first is a no-op here, not a race."""
        result = await db.execute(
            select(Image)
            .options(selectinload(Image.variants))
            .where(Image.status == "pending", Image.deleted_at.is_(None))
            .order_by(Image.updated_at)
            .limit(limit)
        )
        return list(result.scalars().all())

    async def mark_generation_failed(
        self, db: AsyncSession, image: Image, error: str
    ) -> None:
        """Records a terminal generation failure (attempts exhausted) —
        distinct from background.py's per-variant 'failed' rows, which can
        coexist with an overall 'ready' status if only some variants
        failed. This is for the case where the whole job errored before
        producing any rows at all (e.g. the original is unreadable)."""
        generation = dict(image.metadata_.get("generation", {}) or {})
        generation["last_error"] = error
        generation["finished_at"] = datetime.now(UTC).isoformat()
        image.metadata_ = {**image.metadata_, "generation": generation}
        image.status = "failed"
        db.add(image)
        await db.flush()

    async def soft_delete(self, db: AsyncSession, image: Image) -> None:
        image.deleted_at = datetime.now(UTC)
        image.status = "archived"
        db.add(image)
        await db.flush()

    async def reorder(
        self, db: AsyncSession, items: list[tuple[uuid.UUID, int]]
    ) -> None:
        for image_id, sort_order in items:
            await db.execute(
                update(Image).where(Image.id == image_id).values(sort_order=sort_order)
            )
        await db.flush()

    async def set_primary(
        self,
        db: AsyncSession,
        owner_type: str,
        owner_id: uuid.UUID,
        image_id: uuid.UUID,
    ) -> None:
        """Clear is_primary for every image under this owner, then set it on
        *image_id* — generalizes the old per-module set_primary_image to
        every owner_type (product galleries, single-cover collections/
        categories, etc.)."""
        await db.execute(
            update(Image)
            .where(Image.owner_type == owner_type, Image.owner_id == owner_id)
            .values(is_primary=False)
        )
        await db.execute(
            update(Image).where(Image.id == image_id).values(is_primary=True)
        )
        await db.flush()
        db.expire_all()

    # ── Variants ─────────────────────────────────────────────────────────

    async def replace_variants(
        self,
        db: AsyncSession,
        image: Image,
        breakpoint: str,
        variant_rows: list[dict[str, Any]],
    ) -> None:
        """
        Delete any existing variants for *breakpoint* on this image, then
        insert *variant_rows*. Scoped to one breakpoint so a re-crop of a
        single breakpoint (e.g. "mobile") never touches the other
        breakpoints' already-generated variants.
        """
        existing = [v for v in image.variants if v.breakpoint == breakpoint]
        for v in existing:
            await db.delete(v)
        await db.flush()

        for row in variant_rows:
            db.add(ImageVariant(image_id=image.id, **row))
        await db.flush()
        await db.refresh(image, attribute_names=["variants"])

    async def delete_all_variants(self, db: AsyncSession, image: Image) -> None:
        for v in list(image.variants):
            await db.delete(v)
        await db.flush()
        await db.refresh(image, attribute_names=["variants"])

    # ── Bulk URL resolution (for list/detail serializers) ───────────────────

    async def get_primary_variant_urls(
        self,
        db: AsyncSession,
        owner_type: str,
        owner_ids: list[uuid.UUID],
        *,
        variant_name: str = "large",
        breakpoint: str = "desktop",
    ) -> dict[uuid.UUID, str]:
        """
        Bulk-resolve each owner's primary (single-cover) image to one
        variant's cache-busted URL — the replacement for reading a plain
        `image_url` column directly off collections/categories/profiles.
        """
        if not owner_ids:
            return {}
        # Pydantic-validated ids can come back as driver-specific UUID
        # subclasses (e.g. asyncpg.pgproto.pgproto.UUID) rather than plain
        # uuid.UUID — passed as-is into a *new* query's .in_(), SQLAlchemy's
        # bind processor silently fails to match anything instead of
        # erroring. Normalize to stdlib uuid.UUID before binding.
        normalized_ids = [uuid.UUID(str(oid)) for oid in owner_ids]
        result = await db.execute(
            select(Image.owner_id, Image.version, ImageVariant.url)
            .join(ImageVariant, ImageVariant.image_id == Image.id)
            .where(
                Image.owner_type == owner_type,
                Image.owner_id.in_(normalized_ids),
                Image.deleted_at.is_(None),
                Image.is_primary.is_(True),
                ImageVariant.variant_name == variant_name,
                ImageVariant.breakpoint == breakpoint,
                ImageVariant.status == "ready",
            )
        )
        return {row.owner_id: f"{row.url}?v={row.version}" for row in result}

    async def get_primary_image_ids(
        self,
        db: AsyncSession,
        owner_type: str,
        owner_ids: list[uuid.UUID],
    ) -> dict[uuid.UUID, uuid.UUID]:
        """
        Bulk-resolve each owner's primary image id — the single source of
        truth for "does this owner have a primary image", instead of a
        denormalized `primary_image_id` column on the owner's own table.
        Those columns (collections/categories) are never written by the
        generic attach/crop/set-primary/upload flow, which only touches the
        `images` table, so trusting them silently hides a perfectly valid
        primary image. Unlike get_primary_variant_urls, this doesn't require
        a ready variant — an image can be primary before its variants finish
        generating.
        """
        if not owner_ids:
            return {}
        normalized_ids = [uuid.UUID(str(oid)) for oid in owner_ids]
        result = await db.execute(
            select(Image.owner_id, Image.id).where(
                Image.owner_type == owner_type,
                Image.owner_id.in_(normalized_ids),
                Image.deleted_at.is_(None),
                Image.is_primary.is_(True),
            )
        )
        return {row.owner_id: row.id for row in result}
