"""Dump CREATE TABLE DDL for every ORM model (postgresql dialect).

Used to keep supabase/sql files in sync with the SQLAlchemy models.
Usage: python scripts/dump_orm_ddl.py
"""

import importlib
import os
import pkgutil
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

# Minimal env so app.core.config can load without a real .env
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")

from sqlalchemy.dialects import postgresql
from sqlalchemy.schema import CreateIndex, CreateTable

import app.modules as modules_pkg
from app.core.database import Base


def import_all_models() -> None:
    for mod in pkgutil.iter_modules(modules_pkg.__path__):
        name = f"app.modules.{mod.name}.models"
        try:
            importlib.import_module(name)
        except ModuleNotFoundError:
            continue


def main() -> None:
    import_all_models()
    # All business-table FKs resolve to public.profiles; only profiles.id maps
    # to auth.users (a Supabase-managed table not represented in the ORM).
    dialect = postgresql.dialect()
    for table in Base.metadata.sorted_tables:
        if table.schema == "auth":
            continue
        print(str(CreateTable(table).compile(dialect=dialect)).strip() + ";")
        for index in table.indexes:
            print(str(CreateIndex(index).compile(dialect=dialect)).strip() + ";")
        print()


if __name__ == "__main__":
    main()
