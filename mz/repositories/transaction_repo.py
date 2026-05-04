from __future__ import annotations

import sqlite3
from datetime import date, datetime

from mz.models.transaction import InclusionState, Transaction


class TransactionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def create(self, txn: Transaction) -> int:
        cur = self.conn.execute(
            """INSERT INTO transactions
               (primary_raw_id, txn_time, amount_cents, counterparty, description,
                payment_account_id, direction, is_group_payment, inclusion)
               VALUES(?,?,?,?,?,?,?,?,?)""",
            (
                txn.primary_raw_id,
                txn.txn_time.isoformat(),
                txn.amount_cents,
                txn.counterparty,
                txn.description,
                txn.payment_account_id,
                txn.direction,
                int(txn.is_group_payment),
                txn.inclusion,
            ),
        )
        self.conn.commit()
        return cur.lastrowid  # type: ignore[return-value]

    def get_by_id(self, txn_id: int) -> Transaction | None:
        row = self.conn.execute("SELECT * FROM transactions WHERE id=?", (txn_id,)).fetchone()
        return self._from_row(row) if row else None

    def get_by_raw_id(self, raw_id: int) -> Transaction | None:
        row = self.conn.execute(
            "SELECT * FROM transactions WHERE primary_raw_id=?", (raw_id,)
        ).fetchone()
        return self._from_row(row) if row else None

    def list_in_period(
        self,
        period_start: date,
        period_end: date,
        direction: str | None = None,
    ) -> list[Transaction]:
        query = "SELECT * FROM transactions WHERE txn_time >= ? AND txn_time <= ?"
        params: list = [period_start.isoformat(), period_end.isoformat() + "T23:59:59"]
        if direction:
            query += " AND direction=?"
            params.append(direction)
        query += " ORDER BY txn_time DESC"
        rows = self.conn.execute(query, params).fetchall()
        return [self._from_row(r) for r in rows]

    def update_inclusion(
        self, txn_id: int, state: InclusionState, note: str = ""
    ) -> None:
        self.conn.execute(
            """UPDATE transactions
               SET inclusion=?, inclusion_set_at=CURRENT_TIMESTAMP, inclusion_note=?
               WHERE id=?""",
            (state, note, txn_id),
        )
        self.conn.commit()

    def update_category(self, txn_id: int, category_id: int | None) -> None:
        self.conn.execute(
            "UPDATE transactions SET manual_category_id=? WHERE id=?",
            (category_id, txn_id),
        )
        self.conn.commit()

    def exists_for_raw(self, raw_id: int) -> bool:
        row = self.conn.execute(
            "SELECT id FROM transactions WHERE primary_raw_id=?", (raw_id,)
        ).fetchone()
        return row is not None

    def list_dedup_links(self, canonical_id: int) -> list[dict]:
        rows = self.conn.execute(
            """SELECT d.*, r.source, r.txn_time, r.amount_cents, r.counterparty
               FROM dedup_links d
               JOIN raw_transactions r ON r.id = d.raw_txn_id
               WHERE d.canonical_txn_id=?""",
            (canonical_id,),
        ).fetchall()
        return [dict(r) for r in rows]

    def add_dedup_link(
        self,
        canonical_txn_id: int,
        raw_txn_id: int,
        confidence: float,
        reason: str,
        method: str,
    ) -> None:
        try:
            self.conn.execute(
                """INSERT INTO dedup_links
                   (canonical_txn_id, raw_txn_id, match_confidence, match_reason, match_method)
                   VALUES(?,?,?,?,?)""",
                (canonical_txn_id, raw_txn_id, confidence, reason, method),
            )
            self.conn.commit()
        except sqlite3.IntegrityError:
            pass  # already linked

    @staticmethod
    def _from_row(row: sqlite3.Row) -> Transaction:
        txn_time_str = row["txn_time"]
        if isinstance(txn_time_str, bytes):
            txn_time_str = txn_time_str.decode()
        if " " in txn_time_str:
            txn_time_str = txn_time_str.replace(" ", "T")
        return Transaction(
            id=row["id"],
            primary_raw_id=row["primary_raw_id"],
            txn_time=datetime.fromisoformat(txn_time_str),
            amount_cents=row["amount_cents"],
            counterparty=row["counterparty"],
            description=row["description"],
            payment_account_id=row["payment_account_id"],
            direction=row["direction"],
            is_group_payment=bool(row["is_group_payment"]),
            inclusion=row["inclusion"],
            inclusion_note=row["inclusion_note"],
            manual_category_id=row["manual_category_id"],
            notes=row["notes"],
        )
