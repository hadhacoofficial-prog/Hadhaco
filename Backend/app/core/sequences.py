"""Atomic, race-free sequence counters for human-readable IDs.

Replaces the COUNT(...) + format pattern used for order numbers, invoice
numbers, and support ticket numbers — two concurrent requests reading the
same COUNT can format the same next number, either colliding on a unique
constraint deep in checkout (after stock is already reserved) or silently
producing duplicate numbers if the column isn't unique.

A single INSERT ... ON CONFLICT DO UPDATE ... RETURNING is atomic: Postgres
serializes concurrent upserts to the same key via the row's own lock, so two
callers requesting the same key always get distinct, sequential values in
one round trip — no separate SELECT ... FOR UPDATE step needed.
"""

from __future__ import annotations

from sqlalchemy import Integer, String
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.orm import Mapped, mapped_column

from app.core.database import Base


class SequenceCounter(Base):
    __tablename__ = "sequence_counters"

    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    last_value: Mapped[int] = mapped_column(Integer, nullable=False, default=0)


async def next_sequence_value(db: AsyncSession, key: str) -> int:
    """Atomically increment and return the counter for `key`, starting at 1."""
    stmt = (
        pg_insert(SequenceCounter)
        .values(key=key, last_value=1)
        .on_conflict_do_update(
            index_elements=[SequenceCounter.key],
            set_={"last_value": SequenceCounter.last_value + 1},
        )
        .returning(SequenceCounter.last_value)
    )
    result = await db.execute(stmt)
    return result.scalar_one()
