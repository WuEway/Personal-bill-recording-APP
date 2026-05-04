from __future__ import annotations

import sqlite3
from datetime import date

from mz.models.transaction import ImportedFile


class ImportedFileRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def exists_by_hash(self, file_hash: str) -> bool:
        row = self.conn.execute(
            "SELECT id FROM imported_files WHERE file_hash=?", (file_hash,)
        ).fetchone()
        return row is not None

    def create(
        self,
        source: str,
        file_path: str,
        file_hash: str,
        file_format: str,
        is_encrypted: bool,
        period_start: date | None,
        period_end: date | None,
    ) -> int:
        cur = self.conn.execute(
            """INSERT INTO imported_files
               (source, file_path, file_hash, file_format, is_encrypted, period_start, period_end, row_count)
               VALUES(?,?,?,?,?,?,?,0)""",
            (
                source,
                file_path,
                file_hash,
                file_format,
                int(is_encrypted),
                period_start.isoformat() if period_start else None,
                period_end.isoformat() if period_end else None,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def update_row_count(self, file_id: int, count: int) -> None:
        self.conn.execute(
            "UPDATE imported_files SET row_count=? WHERE id=?", (count, file_id)
        )
        self.conn.commit()

    def list_all(self) -> list[ImportedFile]:
        rows = self.conn.execute(
            "SELECT * FROM imported_files ORDER BY imported_at DESC"
        ).fetchall()
        return [self._from_row(r) for r in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> ImportedFile:
        return ImportedFile(
            id=row["id"],
            source=row["source"],
            file_path=row["file_path"],
            file_hash=row["file_hash"],
            file_format=row["file_format"],
            is_encrypted=bool(row["is_encrypted"]),
            period_start=date.fromisoformat(row["period_start"]) if row["period_start"] else None,
            period_end=date.fromisoformat(row["period_end"]) if row["period_end"] else None,
            row_count=row["row_count"],
        )
