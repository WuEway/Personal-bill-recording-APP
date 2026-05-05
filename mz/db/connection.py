from __future__ import annotations

import sqlite3
from pathlib import Path

_DB_PATH: Path | None = None


def set_db_path(path: Path) -> None:
    global _DB_PATH
    _DB_PATH = path


def get_db_path() -> Path:
    if _DB_PATH is not None:
        return _DB_PATH
    default = Path.home() / ".mz" / "data.db"
    default.parent.mkdir(mode=0o700, parents=True, exist_ok=True)
    return default


def get_db() -> sqlite3.Connection:
    path = get_db_path()
    conn = sqlite3.connect(str(path))
    conn.row_factory = sqlite3.Row
    conn.execute("PRAGMA foreign_keys = ON")
    conn.execute("PRAGMA journal_mode = WAL")
    return conn


def init_db(db_path: Path | None = None) -> None:
    if db_path:
        set_db_path(db_path)
        db_path.parent.mkdir(parents=True, exist_ok=True)

    schema_path = Path(__file__).parent / "schema.sql"
    schema_sql = schema_path.read_text(encoding="utf-8")

    conn = get_db()
    try:
        conn.executescript(schema_sql)
        conn.commit()
        # Incremental migrations (safe to run on existing DBs)
        _migrate(conn)
        # Set DB file permissions to 0600 (owner read/write only)
        p = get_db_path()
        if p.exists():
            p.chmod(0o600)
    finally:
        conn.close()


def _migrate(conn: sqlite3.Connection) -> None:
    """Apply additive schema migrations that are safe to re-run."""
    migrations = [
        "ALTER TABLE imported_files ADD COLUMN account_label TEXT",
    ]
    for sql in migrations:
        try:
            conn.execute(sql)
            conn.commit()
        except sqlite3.OperationalError:
            pass  # column already exists
