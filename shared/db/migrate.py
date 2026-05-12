"""
Apply schema.sql to the SQLite database.

Usage:
    python -m shared.db.migrate
"""

from __future__ import annotations

import sqlite3
import sys
from pathlib import Path

_ROOT = Path(__file__).parent.parent.parent
_SCHEMA = Path(__file__).parent / "schema.sql"
_DB_PATH = _ROOT / "data" / "tickets.db"


def migrate(db_path: Path = _DB_PATH) -> None:
    db_path.parent.mkdir(parents=True, exist_ok=True)
    ddl = _SCHEMA.read_text(encoding="utf-8")
    con = sqlite3.connect(db_path)
    try:
        con.executescript(ddl)
        con.commit()
        # Additive column migrations (idempotent via exception swallow)
        _add_column_if_missing(con, "tickets", "human_verified", "INTEGER NOT NULL DEFAULT 0")
        print(f"[OK] Schema applied -> {db_path}")
    finally:
        con.close()


def _add_column_if_missing(con: sqlite3.Connection, table: str, column: str, typedef: str) -> None:
    try:
        con.execute(f"ALTER TABLE {table} ADD COLUMN {column} {typedef}")
        con.commit()
    except sqlite3.OperationalError:
        pass  # column already exists


if __name__ == "__main__":
    migrate()
    sys.exit(0)
