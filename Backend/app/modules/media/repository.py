from __future__ import annotations

import uuid
from datetime import UTC, datetime
from typing import Any

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import selectinload

from app.modules.media.models import Image, ImageVariant


class ImageRepository:
    async def create_image(self, db: AsyncSession, **kwargs: Any) -> Image:
        image = Image(**kwargs)
        db.add(image)
        await db.flush()
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
        await db.refresh(image, attribute_names=["variants"])
        return image

    async def update_fields(
        self, db: AsyncSession, image: Image, data: dict[str, Any]
    ) -> Image:
        for k, v in data.items():
            setattr(image, k, v)
        db.add(image)
        await db.flush()
        await db.refresh(image, attribute_names=["variants"])
        return image

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
