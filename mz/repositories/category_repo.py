from __future__ import annotations

import sqlite3
from datetime import date, datetime

from mz.models.category import ManualCategory, ManualEntry


class CategoryRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    # ── categories ────────────────────────────────────────────────────────
    def create_category(self, cat: ManualCategory) -> int:
        cur = self.conn.execute(
            """INSERT INTO manual_categories(name, icon, monthly_budget_cents, yearly_budget_cents)
               VALUES(?,?,?,?)""",
            (cat.name, cat.icon, cat.monthly_budget_cents, cat.yearly_budget_cents),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_category_by_name(self, name: str) -> ManualCategory | None:
        row = self.conn.execute(
            "SELECT * FROM manual_categories WHERE name=? AND is_active=1", (name,)
        ).fetchone()
        return self._cat_from_row(row) if row else None

    def get_category_by_id(self, cat_id: int) -> ManualCategory | None:
        row = self.conn.execute(
            "SELECT * FROM manual_categories WHERE id=? AND is_active=1", (cat_id,)
        ).fetchone()
        return self._cat_from_row(row) if row else None

    def list_categories(self) -> list[ManualCategory]:
        rows = self.conn.execute(
            "SELECT * FROM manual_categories WHERE is_active=1 ORDER BY name"
        ).fetchall()
        return [self._cat_from_row(r) for r in rows]

    def update_budget(
        self,
        cat_id: int,
        monthly_cents: int | None,
        yearly_cents: int | None,
    ) -> None:
        self.conn.execute(
            "UPDATE manual_categories SET monthly_budget_cents=?, yearly_budget_cents=? WHERE id=?",
            (monthly_cents, yearly_cents, cat_id),
        )
        self.conn.commit()

    def deactivate_category(self, cat_id: int) -> None:
        self.conn.execute(
            "UPDATE manual_categories SET is_active=0 WHERE id=?", (cat_id,)
        )
        self.conn.commit()

    # ── entries ───────────────────────────────────────────────────────────
    def create_entry(self, entry: ManualEntry) -> int:
        cur = self.conn.execute(
            """INSERT INTO manual_entries(category_id, txn_time, amount_cents, description, linked_txn_id)
               VALUES(?,?,?,?,?)""",
            (
                entry.category_id,
                entry.txn_time.isoformat(),
                entry.amount_cents,
                entry.description,
                entry.linked_txn_id,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def list_entries(
        self,
        category_id: int | None = None,
        period_start: date | None = None,
        period_end: date | None = None,
    ) -> list[ManualEntry]:
        query = "SELECT * FROM manual_entries WHERE 1=1"
        params: list = []
        if category_id is not None:
            query += " AND category_id=?"
            params.append(category_id)
        if period_start:
            query += " AND txn_time >= ?"
            params.append(period_start.isoformat())
        if period_end:
            query += " AND txn_time <= ?"
            params.append(period_end.isoformat() + "T23:59:59")
        query += " ORDER BY txn_time DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [self._entry_from_row(r) for r in rows]

    def delete_entry(self, entry_id: int) -> bool:
        cur = self.conn.execute("DELETE FROM manual_entries WHERE id=?", (entry_id,))
        self.conn.commit()
        return cur.rowcount > 0

    def sum_entries_in_period(self, category_id: int, start: date, end: date) -> int:
        row = self.conn.execute(
            """SELECT COALESCE(SUM(amount_cents), 0) as total
               FROM manual_entries
               WHERE category_id=? AND txn_time >= ? AND txn_time <= ?""",
            (category_id, start.isoformat(), end.isoformat() + "T23:59:59"),
        ).fetchone()
        return row["total"]

    @staticmethod
    def _cat_from_row(row: sqlite3.Row) -> ManualCategory:
        return ManualCategory(
            id=row["id"],
            name=row["name"],
            icon=row["icon"],
            monthly_budget_cents=row["monthly_budget_cents"],
            yearly_budget_cents=row["yearly_budget_cents"],
            is_active=bool(row["is_active"]),
        )

    @staticmethod
    def _entry_from_row(row: sqlite3.Row) -> ManualEntry:
        txn_time_str = row["txn_time"]
        if isinstance(txn_time_str, bytes):
            txn_time_str = txn_time_str.decode()
        if " " in txn_time_str:
            txn_time_str = txn_time_str.replace(" ", "T")
        return ManualEntry(
            id=row["id"],
            category_id=row["category_id"],
            txn_time=datetime.fromisoformat(txn_time_str),
            amount_cents=row["amount_cents"],
            description=row["description"],
            linked_txn_id=row["linked_txn_id"],
        )
