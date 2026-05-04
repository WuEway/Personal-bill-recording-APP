from __future__ import annotations

import sqlite3
from datetime import date, datetime

from mz.models.transaction import RawTransaction, RawTransactionDraft


class RawTransactionRepository:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn

    def insert(
        self,
        draft: RawTransactionDraft,
        source_file_id: int,
        payment_account_id: int | None,
    ) -> int | None:
        """Insert raw transaction; return id or None if duplicate (unique constraint)."""
        try:
            cur = self.conn.execute(
                """INSERT INTO raw_transactions
                   (source, source_file_id, txn_time, amount_cents, currency,
                    counterparty, description, payment_account_id, txn_type_raw,
                    direction, external_txn_id, external_merchant_id, raw_json,
                    is_group_payment)
                   VALUES(?,?,?,?,?,?,?,?,?,?,?,?,?,?)""",
                (
                    draft.source,
                    source_file_id,
                    draft.txn_time.isoformat(),
                    draft.amount_cents,
                    draft.currency,
                    draft.counterparty,
                    draft.description,
                    payment_account_id,
                    draft.txn_type_raw,
                    draft.direction,
                    draft.external_txn_id,
                    draft.external_merchant_id,
                    draft.raw_json_str(),
                    int(draft.is_group_payment),
                ),
            )
            self.conn.commit()
            return cur.lastrowid
        except sqlite3.IntegrityError:
            return None  # duplicate external_txn_id

    def mark_internal_transfer(self, raw_id: int, reason: str) -> None:
        self.conn.execute(
            "UPDATE raw_transactions SET is_internal_transfer=1, transfer_reason=? WHERE id=?",
            (reason, raw_id),
        )
        self.conn.commit()

    def list_by_source_file(self, source_file_id: int) -> list[RawTransaction]:
        rows = self.conn.execute(
            "SELECT * FROM raw_transactions WHERE source_file_id=?", (source_file_id,)
        ).fetchall()
        return [self._from_row(r) for r in rows]

    def list_in_period(
        self,
        period_start: date,
        period_end: date,
        source: str | None = None,
        direction: str | None = None,
    ) -> list[RawTransaction]:
        query = "SELECT * FROM raw_transactions WHERE txn_time >= ? AND txn_time <= ?"
        params: list = [period_start.isoformat(), (period_end.isoformat() + "T23:59:59")]
        if source:
            query += " AND source=?"
            params.append(source)
        if direction:
            query += " AND direction=?"
            params.append(direction)
        query += " ORDER BY txn_time"
        rows = self.conn.execute(query, params).fetchall()
        return [self._from_row(r) for r in rows]

    def get_by_id(self, raw_id: int) -> RawTransaction | None:
        row = self.conn.execute("SELECT * FROM raw_transactions WHERE id=?", (raw_id,)).fetchone()
        return self._from_row(row) if row else None

    def list_unlinked_expenses(
        self,
        period_start: date,
        period_end: date,
        shadow_source: str,
    ) -> list[RawTransaction]:
        """Bank shadow candidates: expense rows not yet in dedup_links."""
        rows = self.conn.execute(
            """SELECT r.* FROM raw_transactions r
               LEFT JOIN dedup_links d ON d.raw_txn_id = r.id
               WHERE r.source=? AND r.direction='expense'
                 AND r.is_internal_transfer=0
                 AND r.txn_time >= ? AND r.txn_time <= ?
                 AND d.id IS NULL
               ORDER BY r.txn_time""",
            (
                shadow_source,
                period_start.isoformat(),
                period_end.isoformat() + "T23:59:59",
            ),
        ).fetchall()
        return [self._from_row(r) for r in rows]

    @staticmethod
    def _from_row(row: sqlite3.Row) -> RawTransaction:
        txn_time_str = row["txn_time"]
        if isinstance(txn_time_str, bytes):
            txn_time_str = txn_time_str.decode()
        txn_time_str = txn_time_str.replace(" ", "T") if " " in txn_time_str else txn_time_str
        return RawTransaction(
            id=row["id"],
            source=row["source"],
            source_file_id=row["source_file_id"],
            txn_time=datetime.fromisoformat(txn_time_str),
            amount_cents=row["amount_cents"],
            currency=row["currency"],
            counterparty=row["counterparty"],
            description=row["description"],
            payment_account_id=row["payment_account_id"],
            txn_type_raw=row["txn_type_raw"],
            direction=row["direction"],
            external_txn_id=row["external_txn_id"],
            external_merchant_id=row["external_merchant_id"],
            raw_json=row["raw_json"],
            is_internal_transfer=bool(row["is_internal_transfer"]),
            transfer_reason=row["transfer_reason"],
            is_group_payment=bool(row["is_group_payment"]),
            is_refund=bool(row["is_refund"]),
        )
