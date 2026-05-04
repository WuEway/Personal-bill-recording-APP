from __future__ import annotations

import sqlite3
from pathlib import Path

from mz.db.connection import get_db, init_db, set_db_path


def get_connection(db_path: Path | None = None) -> sqlite3.Connection:
    if db_path:
        set_db_path(db_path)
    init_db()
    return get_db()


def get_user_name(conn: sqlite3.Connection) -> str | None:
    row = conn.execute("SELECT value FROM app_config WHERE key='user_name'").fetchone()
    return row[0] if row else None


def is_onboarded(conn: sqlite3.Connection) -> bool:
    row = conn.execute("SELECT value FROM app_config WHERE key='onboarded'").fetchone()
    return row is not None and row[0] == "1"
