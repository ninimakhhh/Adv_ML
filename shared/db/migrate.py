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
        print(f"[OK] Schema applied -> {db_path}")
    finally:
        con.close()


if __name__ == "__main__":
    migrate()
    sys.exit(0)
