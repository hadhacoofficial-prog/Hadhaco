"""Static sanity check of setup.sql.

Verifies that every included file exists and that FK targets, RLS/policy
tables, and trigger tables are created before they are referenced, in
setup.sql include order. Complements the CI job that runs setup.sql against
a real PostgreSQL.

Usage: python scripts/check_sql_order.py
"""

import re
import sys
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "supabase" / "sql"


def norm(name: str) -> str:
    return name.replace("public.", "").lower()


def main() -> int:
    setup = (SQL_DIR / "setup.sql").read_text(encoding="utf-8")
    order = re.findall(r"^\\i (\S+)", setup, re.MULTILINE)

    missing = [f for f in order if not (SQL_DIR / f).exists()]
    print("include files missing:", missing or "none")

    created: set[str] = {"auth.users"}  # Supabase-managed
    problems: list[str] = []

    for fname in order:
        text = (SQL_DIR / fname).read_text(encoding="utf-8")
        text = re.sub(r"--.*", "", text)

        for m in re.finditer(
            r"CREATE (?:TABLE|VIEW|MATERIALIZED VIEW)(?: IF NOT EXISTS)?\s+(?:public\.)?([a-z_0-9]+)",
            text,
            re.I,
        ):
            created.add(norm(m.group(1)))
        for m in re.finditer(
            r"CREATE OR REPLACE (?:VIEW|MATERIALIZED VIEW)\s+(?:public\.)?([a-z_0-9]+)",
            text,
            re.I,
        ):
            created.add(norm(m.group(1)))

        for m in re.finditer(
            r"\bREFERENCES\s+((?:public\.|auth\.)?[a-z_0-9]+)", text, re.I
        ):
            ref = m.group(1).lower()
            ref = ref if ref.startswith("auth.") else norm(ref)
            if ref not in created:
                problems.append(f"{fname}: FK references missing table {ref}")

        for m in re.finditer(
            r"ALTER TABLE\s+(?:ONLY\s+)?((?:public\.)?[a-z_0-9]+)\s+ENABLE ROW",
            text,
            re.I,
        ):
            if norm(m.group(1)) not in created:
                problems.append(f"{fname}: RLS on missing table {m.group(1)}")

        for m in re.finditer(
            r"CREATE POLICY\s+\"[^\"]+\"\s+ON\s+((?:public\.)?[a-z_0-9]+)", text, re.I
        ):
            if norm(m.group(1)) not in created:
                problems.append(f"{fname}: policy on missing table {m.group(1)}")

        for m in re.finditer(
            r"CREATE TRIGGER\s+\w+\s+(?:BEFORE|AFTER)\s+[\w\s,]+?\bON\s+((?:public\.|auth\.)?[a-z_0-9]+)",
            text,
            re.I,
        ):
            ref = m.group(1).lower()
            ref = ref if ref.startswith("auth.") else norm(ref)
            if ref not in created:
                problems.append(f"{fname}: trigger on missing table {ref}")

    if problems:
        print("problems:")
        for p in problems:
            print(" -", p)
        return 1
    print("no dependency problems")
    return 0


if __name__ == "__main__":
    sys.exit(main())
