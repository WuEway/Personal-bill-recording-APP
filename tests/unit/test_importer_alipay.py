from __future__ import annotations

from pathlib import Path

import pytest

from mz.importer.alipay import AlipayCsvImporter
from tests.conftest import make_alipay_csv


def test_parse_expense(tmp_path: Path):
    path = make_alipay_csv(tmp_path, [
        {"sign": "支出", "amount": "103.08", "party": "某商户", "txn_id": "ALIPAY001"},
    ])
    importer = AlipayCsvImporter()
    drafts = list(importer.parse(path, "csv"))
    assert len(drafts) == 1
    d = drafts[0]
    assert d.direction == "expense"
    assert d.amount_cents == -10308
    assert d.source == "alipay"


def test_parse_income(tmp_path: Path):
    path = make_alipay_csv(tmp_path, [
        {"sign": "收入", "amount": "500.00", "party": "退款方"},
    ])
    importer = AlipayCsvImporter()
    drafts = list(importer.parse(path, "csv"))
    assert len(drafts) == 1
    assert drafts[0].direction == "income"
    assert drafts[0].amount_cents == 50000


def test_parse_no_count_transfer(tmp_path: Path):
    path = make_alipay_csv(tmp_path, [
        {"sign": "不计收支", "amount": "200.00"},
    ])
    importer = AlipayCsvImporter()
    drafts = list(importer.parse(path, "csv"))
    assert len(drafts) == 1
    assert drafts[0].direction == "transfer"


def test_parse_zero_amount_as_transfer(tmp_path: Path):
    path = make_alipay_csv(tmp_path, [
        {"sign": "支出", "amount": "0.00"},
    ])
    importer = AlipayCsvImporter()
    drafts = list(importer.parse(path, "csv"))
    assert len(drafts) == 1
    assert drafts[0].direction == "transfer"
    assert drafts[0].amount_cents == 0


def test_mixed_payment_split(tmp_path: Path):
    path = make_alipay_csv(tmp_path, [
        {"sign": "支出", "amount": "50.00", "payment": "工商银行储蓄卡(6930)&红包"},
    ])
    importer = AlipayCsvImporter()
    drafts = list(importer.parse(path, "csv"))
    assert len(drafts) == 1
    # primary payment is everything before &
    assert drafts[0].payment_method_raw == "工商银行储蓄卡(6930)"


def test_gbk_encoding(tmp_path: Path):
    """File with GBK encoding should parse correctly."""
    path = make_alipay_csv(tmp_path, [
        {"sign": "支出", "amount": "10.00", "party": "外卖商家"},
    ])
    importer = AlipayCsvImporter()
    assert importer.detect(path, "csv")
    drafts = list(importer.parse(path, "csv"))
    assert len(drafts) >= 1
