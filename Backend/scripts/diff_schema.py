"""Compare ORM model columns against supabase/sql CREATE TABLE definitions.

Reports, per table: columns the SQL is missing, and SQL-only columns the ORM
does not know about. Crude SQL parsing — good enough for drift detection.
Usage: python scripts/diff_schema.py
"""

import importlib
import os
import pkgutil
import re
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
os.environ.setdefault("DATABASE_URL", "postgresql+asyncpg://x:x@localhost/x")

import app.modules as modules_pkg
from app.core.database import Base

SQL_DIR = Path(__file__).resolve().parent.parent / "supabase" / "sql"

SQL_KEYWORDS = {
    "primary",
    "foreign",
    "unique",
    "check",
    "constraint",
    "exclude",
    "like",
}


def import_all_models() -> None:
    for mod in pkgutil.iter_modules(modules_pkg.__path__):
        try:
            importlib.import_module(f"app.modules.{mod.name}.models")
        except ModuleNotFoundError:
            continue


def parse_sql_tables() -> dict[str, tuple[str, set[str]]]:
    """Return {table_name: (file, {column, ...})}."""
    tables: dict[str, tuple[str, set[str]]] = {}
    pattern = re.compile(
        r"CREATE TABLE (?:IF NOT EXISTS )?(?:public\.)?([a-z_0-9]+)\s*\((.*?)\n\);",
        re.IGNORECASE | re.DOTALL,
    )
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        text = sql_file.read_text(encoding="utf-8")
        for match in pattern.finditer(text):
            name, body = match.group(1), match.group(2)
            cols: set[str] = set()
            depth = 0
            for raw_line in body.splitlines():
                line = re.sub(r"--.*$", "", raw_line).strip()
                if not line:
                    continue
                if depth == 0:
                    first = re.match(r"^([a-z_][a-z_0-9]*)", line, re.IGNORECASE)
                    if first and first.group(1).lower() not in SQL_KEYWORDS:
                        cols.add(first.group(1).lower())
                depth += line.count("(") - line.count(")")
            tables[name] = (sql_file.name, cols)
    return tables


def main() -> None:
    import_all_models()
    sql_tables = parse_sql_tables()
    orm_tables = {
        t.name: {c.name for c in t.columns} for t in Base.metadata.tables.values()
    }

    missing_tables = sorted(set(orm_tables) - set(sql_tables))
    if missing_tables:
        print("== TABLES MISSING FROM SQL ==")
        for t in missing_tables:
            print(f"  {t}")
        print()

    for name in sorted(orm_tables):
        if name not in sql_tables:
            continue
        sql_file, sql_cols = sql_tables[name]
        orm_cols = orm_tables[name]
        missing = sorted(orm_cols - sql_cols)
        extra = sorted(sql_cols - orm_cols)
        if missing or extra:
            print(f"== {name} ({sql_file}) ==")
            if missing:
                print(f"  SQL missing: {', '.join(missing)}")
            if extra:
                print(f"  SQL extra:   {', '.join(extra)}")


if __name__ == "__main__":
    main()
