"""get_images_for_products must hydrate list-view images in ONE statement.

It used to take three round trips (rank ids, load images, selectinload
variants); on a cold /products cache miss each trip to the remote DB costs
~100-250ms. This pins the single-statement shape and the grouping/ordering.
"""

from __future__ import annotations

import uuid
from types import SimpleNamespace
from unittest.mock import AsyncMock, MagicMock

from sqlalchemy.dialects import postgresql

from app.core.model_registry import import_all_models

import_all_models()

from app.modules.catalog.repository import ProductRepository  # noqa: E402


def _db_returning(images: list) -> MagicMock:
    result = MagicMock()
    result.unique.return_value.scalars.return_value.all.return_value = images
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)
    return db


async def test_single_statement_and_grouped_by_owner_in_rank_order():
    p1, p2 = uuid.uuid4(), uuid.uuid4()
    imgs = [
        SimpleNamespace(id=1, owner_id=p1),
        SimpleNamespace(id=2, owner_id=p1),
        SimpleNamespace(id=3, owner_id=p2),
        SimpleNamespace(id=4, owner_id=None),  # orphan row is ignored
    ]
    db = _db_returning(imgs)

    mapping = await ProductRepository().get_images_for_products(db, [p1, p2])

    assert db.execute.await_count == 1
    assert [i.id for i in mapping[p1]] == [1, 2]
    assert [i.id for i in mapping[p2]] == [3]
    assert None not in mapping


async def test_statement_ranks_in_sql_and_joins_variants():
    db = _db_returning([])
    await ProductRepository().get_images_for_products(db, [uuid.uuid4()])

    stmt = db.execute.await_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect())).lower()

    assert "row_number() over" in sql
    assert "partition by images.owner_id" in sql or "partition by" in sql
    assert "left outer join" in sql  # joined-loaded Image.variants
    assert "_rn <=" in sql or "_rn" in sql


async def test_empty_product_ids_makes_no_query():
    db = _db_returning([])
    assert await ProductRepository().get_images_for_products(db, []) == {}
    db.execute.assert_not_awaited()


async def test_list_paginated_without_variants_is_one_statement_with_stock_column():
    """load_variants=False folds availability into the list statement."""
    from app.modules.catalog.repository import ProductRepository as Repo

    prod = SimpleNamespace(id=uuid.uuid4())
    row = (prod, 1, 7)  # (Product, total, _avail)
    result = MagicMock()
    result.unique.return_value.all.return_value = [row]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    items, total = await Repo().list_paginated(db, page=1, load_variants=False)

    assert db.execute.await_count == 1
    assert total == 1
    assert items[0].list_available_stock == 7

    stmt = db.execute.await_args.args[0]
    sql = str(stmt.compile(dialect=postgresql.dialect())).lower()
    assert "_avail" in sql
    assert "product_variants" in sql  # correlated availability subquery


async def test_list_paginated_default_still_loads_variants_for_other_callers():
    from app.modules.catalog.repository import ProductRepository as Repo

    prod = SimpleNamespace(id=uuid.uuid4())
    result = MagicMock()
    result.unique.return_value.all.return_value = [(prod, 1)]
    db = MagicMock()
    db.execute = AsyncMock(return_value=result)

    items, _ = await Repo().list_paginated(db, page=1)

    assert not hasattr(items[0], "list_available_stock")
    stmt = db.execute.await_args.args[0]
    assert "_avail" not in str(stmt.compile(dialect=postgresql.dialect())).lower()
