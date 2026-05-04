from __future__ import annotations

from datetime import datetime
from pathlib import Path

import pytest

from mz.importer.wechat import WechatImporter
from tests.conftest import make_wechat_xlsx


def test_parse_expense_row(tmp_path: Path):
    path = make_wechat_xlsx(tmp_path, [
        {"time": datetime(2026, 4, 15, 12, 0, 0), "sign": "支出", "amount": 99.0,
         "party": "深圳大学城校园服务", "txn_id": "TXN001"},
    ])
    importer = WechatImporter()
    drafts = list(importer.parse(path, "xlsx"))
    assert len(drafts) == 1
    d = drafts[0]
    assert d.direction == "expense"
    assert d.amount_cents == -9900
    assert d.counterparty == "深圳大学城校园服务"
    assert d.external_txn_id == "TXN001"
    assert d.source == "wechat"


def test_parse_income_row(tmp_path: Path):
    path = make_wechat_xlsx(tmp_path, [
        {"sign": "收入", "amount": 78.34, "party": "王腾"},
    ])
    importer = WechatImporter()
    drafts = list(importer.parse(path, "xlsx"))
    assert len(drafts) == 1
    d = drafts[0]
    assert d.direction == "income"
    assert d.amount_cents == 7834


def test_parse_group_payment(tmp_path: Path):
    path = make_wechat_xlsx(tmp_path, [
        {"type": "群收款", "sign": "支出", "amount": 238.34},
    ])
    importer = WechatImporter()
    drafts = list(importer.parse(path, "xlsx"))
    assert len(drafts) == 1
    assert drafts[0].is_group_payment is True


def test_parse_transfer_neutral(tmp_path: Path):
    """'/' sign → transfer direction."""
    path = make_wechat_xlsx(tmp_path, [
        {"sign": "/", "amount": 100.0, "type": "零钱充值"},
    ])
    importer = WechatImporter()
    drafts = list(importer.parse(path, "xlsx"))
    assert len(drafts) == 1
    assert drafts[0].direction == "transfer"


def test_detect_period(tmp_path: Path):
    from datetime import date

    path = make_wechat_xlsx(tmp_path, [
        {"time": datetime(2026, 4, 1, 10, 0, 0), "sign": "支出", "amount": 10.0},
        {"time": datetime(2026, 4, 30, 22, 0, 0), "sign": "支出", "amount": 20.0},
    ])
    importer = WechatImporter()
    start, end = importer.detect_period(path, "xlsx")
    assert start == date(2026, 4, 1)
    assert end == date(2026, 4, 30)
