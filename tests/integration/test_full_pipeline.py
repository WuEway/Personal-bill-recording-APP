from __future__ import annotations

from datetime import date
from pathlib import Path

import pytest

from mz.services.import_service import ImportService
from mz.services.dedupe.engine import DedupeEngine
from mz.services.inclusion import InclusionManager
from mz.repositories.raw_txn_repo import RawTransactionRepository
from mz.repositories.transaction_repo import TransactionRepository
from tests.conftest import make_wechat_xlsx, make_alipay_csv


def test_import_and_dedupe_pipeline(conn, tmp_path: Path):
    """Full pipeline: import wechat + alipay files, dedupe, compute totals."""
    wechat_file = make_wechat_xlsx(tmp_path, [
        {"time": __import__("datetime").datetime(2026, 4, 15, 10), "sign": "支出", "amount": 99.0,
         "party": "深圳大学城", "payment": "平安银行储蓄卡(8223)", "txn_id": "W001"},
        {"time": __import__("datetime").datetime(2026, 4, 20, 14), "sign": "支出", "amount": 6.0,
         "party": "怪兽充电", "payment": "零钱", "txn_id": "W002"},
        {"time": __import__("datetime").datetime(2026, 4, 25, 18), "sign": "收入", "amount": 78.34,
         "party": "王腾", "txn_id": "W003"},
    ])
    alipay_file = make_alipay_csv(tmp_path, [
        {"time": "2026-04-18 09:00:00", "sign": "支出", "amount": "50.00",
         "party": "外卖商家", "txn_id": "A001"},
        {"time": "2026-04-20 11:00:00", "sign": "不计收支", "amount": "100.00",
         "party": "余额宝", "txn_id": "A002"},
    ])

    svc = ImportService(conn)
    r1 = svc.import_file(wechat_file)
    r2 = svc.import_file(alipay_file)

    assert r1[0].rows_inserted == 3
    assert r2[0].rows_inserted == 2

    # Dedupe
    engine = DedupeEngine(conn)
    stats = engine.run(date(2026, 4, 1), date(2026, 4, 30))
    assert stats["created"] > 0

    # Compute totals
    mgr = InclusionManager(conn)
    total = mgr.compute_total(date(2026, 4, 1), date(2026, 4, 30))

    # 99 (wechat) + 6 (wechat) + 50 (alipay) = 155 yuan = 15500 cents
    # Alipay "不计收支" transfer and WeChat income are NOT counted
    assert total.raw_expense_cents == 15500


def test_duplicate_import_skipped(conn, tmp_path: Path):
    """Importing the same file twice should be a no-op."""
    from datetime import datetime

    wechat_file = make_wechat_xlsx(tmp_path, [
        {"time": datetime(2026, 4, 15), "sign": "支出", "amount": 10.0, "txn_id": "DUP001"},
    ])
    svc = ImportService(conn)
    r1 = svc.import_file(wechat_file)
    r2 = svc.import_file(wechat_file)

    assert r1[0].rows_inserted == 1
    assert r2[0].skipped_duplicate is True


def test_internal_transfer_not_counted(conn, tmp_path: Path):
    from datetime import datetime

    wechat_file = make_wechat_xlsx(tmp_path, [
        {"time": datetime(2026, 4, 15), "sign": "支出", "amount": 100.0,
         "type": "信用卡还款", "txn_id": "CC001"},
        {"time": datetime(2026, 4, 16), "sign": "支出", "amount": 50.0,
         "party": "外卖", "txn_id": "EX001"},
    ])
    svc = ImportService(conn)
    svc.import_file(wechat_file)

    raw_repo = RawTransactionRepository(conn)
    raws = raw_repo.list_in_period(date(2026, 4, 1), date(2026, 4, 30))
    internal = [r for r in raws if r.is_internal_transfer]
    assert len(internal) == 1
    assert internal[0].transfer_reason == "cc_repayment"
