from __future__ import annotations

from datetime import datetime, date

import pytest

from mz.models.transaction import Transaction
from mz.repositories.transaction_repo import TransactionRepository
from mz.repositories.raw_txn_repo import RawTransactionRepository
from mz.repositories.imported_file_repo import ImportedFileRepository
from mz.services.inclusion import InclusionManager


def _insert_raw(conn, direction="expense", is_group=False):
    """Insert a minimal raw transaction and return its id."""
    file_repo = ImportedFileRepository(conn)
    file_id = file_repo.create("wechat", "/tmp/test.xlsx", f"hash_{direction}_{is_group}", "xlsx", False, None, None)
    conn.execute(
        """INSERT INTO raw_transactions
           (source, source_file_id, txn_time, amount_cents, direction, is_group_payment, raw_json)
           VALUES(?,?,?,?,?,?,?)""",
        ("wechat", file_id, "2026-04-15T12:00:00", 1000, direction, int(is_group), "{}"),
    )
    conn.commit()
    return conn.execute("SELECT last_insert_rowid()").fetchone()[0]


def _insert_txn(conn, direction="expense", is_group=False, inclusion="auto"):
    raw_id = _insert_raw(conn, direction, is_group)
    txn_repo = TransactionRepository(conn)
    txn = Transaction(
        primary_raw_id=raw_id,
        txn_time=datetime(2026, 4, 15),
        amount_cents=1000,
        direction=direction,
        is_group_payment=is_group,
        inclusion=inclusion,
    )
    return txn_repo.create(txn)


# ── effective logic ──────────────────────────────────────────────────────


def test_expense_auto_counts_in(conn):
    mgr = InclusionManager(conn)
    tid = _insert_txn(conn, direction="expense", is_group=False, inclusion="auto")
    total = mgr.compute_total(date(2026, 4, 1), date(2026, 4, 30))
    assert total.raw_expense_cents == 1000


def test_group_payment_auto_excluded(conn):
    mgr = InclusionManager(conn)
    _insert_txn(conn, direction="expense", is_group=True, inclusion="auto")
    total = mgr.compute_total(date(2026, 4, 1), date(2026, 4, 30))
    assert total.raw_expense_cents == 0


def test_income_auto_not_counted(conn):
    mgr = InclusionManager(conn)
    _insert_txn(conn, direction="income", inclusion="auto")
    total = mgr.compute_total(date(2026, 4, 1), date(2026, 4, 30))
    assert total.raw_expense_cents == 0
    assert total.offset_income_cents == 0


def test_income_offset_subtracts(conn):
    mgr = InclusionManager(conn)
    raw_id = _insert_raw(conn, direction="income")
    txn_repo = TransactionRepository(conn)
    txn_id = txn_repo.create(Transaction(
        primary_raw_id=raw_id,
        txn_time=datetime(2026, 4, 15),
        amount_cents=500,
        direction="income",
        inclusion="offset",
    ))
    total = mgr.compute_total(date(2026, 4, 1), date(2026, 4, 30))
    assert total.offset_income_cents == 500
    assert total.total_expense_cents == -500  # 0 expense - 500 offset


def test_set_offset_on_expense_raises(conn):
    mgr = InclusionManager(conn)
    tid = _insert_txn(conn, direction="expense")
    with pytest.raises(ValueError, match="offset"):
        mgr.set(tid, "offset")


def test_explicit_excluded(conn):
    mgr = InclusionManager(conn)
    tid = _insert_txn(conn, direction="expense")
    mgr.set(tid, "excluded")
    total = mgr.compute_total(date(2026, 4, 1), date(2026, 4, 30))
    assert total.raw_expense_cents == 0
    assert total.excluded_count == 1


def test_reset_to_auto(conn):
    mgr = InclusionManager(conn)
    tid = _insert_txn(conn, direction="expense")
    mgr.set(tid, "excluded")
    mgr.reset(tid)
    total = mgr.compute_total(date(2026, 4, 1), date(2026, 4, 30))
    assert total.raw_expense_cents == 1000
