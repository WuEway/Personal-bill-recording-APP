from __future__ import annotations

from datetime import datetime

import pytest

from mz.models.transaction import RawTransaction
from mz.services.transfer_detector import TransferDetector


def make_raw(**kwargs) -> RawTransaction:
    defaults = dict(
        id=1,
        source="wechat",
        source_file_id=1,
        txn_time=datetime(2026, 4, 15),
        amount_cents=-1000,
        direction="expense",
        raw_json="{}",
    )
    defaults.update(kwargs)
    return RawTransaction(**defaults)


def test_credit_card_repayment():
    t = make_raw(txn_type_raw="信用卡还款", direction="expense")
    assert TransferDetector().detect(t) == "cc_repayment"


def test_huabei_repayment():
    t = make_raw(counterparty="花呗", description="花呗还款", direction="expense")
    assert TransferDetector().detect(t) == "huabei_repayment"


def test_yuebao_purchase():
    t = make_raw(counterparty="余额宝", amount_cents=-5000, direction="expense")
    assert TransferDetector().detect(t) == "yuebao_purchase"


def test_withdrawal():
    t = make_raw(txn_type_raw="微信零钱提现", direction="expense")
    assert TransferDetector().detect(t) == "withdrawal"


def test_self_transfer():
    t = make_raw(counterparty="吴逸威", direction="expense")
    detector = TransferDetector(user_name="吴逸威")
    assert detector.detect(t) == "self_transfer"


def test_normal_expense_not_transfer():
    t = make_raw(counterparty="外卖商家", description="外卖", direction="expense")
    assert TransferDetector().detect(t) is None


def test_source_level_transfer():
    t = make_raw(direction="transfer", txn_type_raw=None)
    reason = TransferDetector().detect(t)
    assert reason is not None  # caught by source_transfer rule
