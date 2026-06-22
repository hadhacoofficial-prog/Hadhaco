"""One-shot fixer for supabase/sql files.

1. `CREATE POLICY IF NOT EXISTS` is not valid PostgreSQL — rewrite to
   `DROP POLICY IF EXISTS ...; CREATE POLICY ...`.
2. Unguarded `CREATE TRIGGER` fails on re-run — prepend `DROP TRIGGER IF EXISTS`.

Usage: python scripts/fix_sql_idempotency.py
"""

import re
from pathlib import Path

SQL_DIR = Path(__file__).resolve().parent.parent / "supabase" / "sql"

POLICY_RE = re.compile(
    r'CREATE POLICY (?:IF NOT EXISTS )?("[^"]+")\s+ON\s+([a-zA-Z_.]+)',
    re.DOTALL,
)
TRIGGER_RE = re.compile(
    r"(?<!OR REPLACE )CREATE TRIGGER (\w+)\s*\n((?:[^\n;]*\n)*?[^\n;]*?\bON\s+([a-zA-Z_.]+))"
)


def fix_policies(text: str) -> str:
    out = []
    last = 0
    for m in POLICY_RE.finditer(text):
        name, table = m.group(1), m.group(2)
        # skip if the preceding line already has the guard
        prev = text[: m.start()].rstrip().splitlines()
        if prev and f"DROP POLICY IF EXISTS {name}" in prev[-1]:
            continue
        out.append(text[last : m.start()])
        out.append(
            f"DROP POLICY IF EXISTS {name} ON {table};\nCREATE POLICY {name} ON {table}"
        )
        last = m.end()
    out.append(text[last:])
    return "".join(out)


def fix_triggers(text: str) -> str:
    out = []
    for m in re.finditer(r"^CREATE TRIGGER (\w+)", text, re.MULTILINE):
        # find the ON <table> within the statement (up to the terminating ;)
        stmt_end = text.find(";", m.start())
        stmt = text[m.start() : stmt_end]
        on = re.search(r"\bON\s+([a-zA-Z_][a-zA-Z_0-9.]*)", stmt)
        if not on:
            continue
        guard = f"DROP TRIGGER IF EXISTS {m.group(1)} ON {on.group(1)};\n"
        # skip if the previous line already drops this trigger
        prev = text[: m.start()].rstrip().splitlines()
        if prev and f"DROP TRIGGER IF EXISTS {m.group(1)}" in prev[-1]:
            continue
        out.append((m.start(), guard))
    for start, guard in reversed(out):
        text = text[:start] + guard + text[start:]
    return text


def main() -> None:
    for sql_file in sorted(SQL_DIR.glob("*.sql")):
        original = sql_file.read_text(encoding="utf-8")
        fixed = fix_triggers(fix_policies(original))
        if fixed != original:
            sql_file.write_text(fixed, encoding="utf-8")
            print(f"fixed: {sql_file.name}")


if __name__ == "__main__":
    main()
