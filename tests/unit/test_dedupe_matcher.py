from __future__ import annotations

from datetime import datetime

from mz.models.transaction import RawTransaction
from mz.services.dedupe.matcher import can_match, is_app_shadow_in_bank


def raw(source="wechat", amount=-9900, direction="expense", date_=None, last_4=None):
    return RawTransaction(
        id=1,
        source=source,
        source_file_id=1,
        txn_time=date_ or datetime(2026, 4, 15),
        amount_cents=amount,
        direction=direction,
        raw_json="{}",
    )


def test_exact_match():
    primary = raw("wechat", -9900, "expense", datetime(2026, 4, 15))
    shadow = raw("bank_pingan", -9900, "expense", datetime(2026, 4, 15))
    ok, conf, reason = can_match(primary, shadow, "8223", "8223", "平安银行", "平安银行")
    assert ok
    assert conf == 1.0


def test_amount_mismatch():
    primary = raw("wechat", -9900)
    shadow = raw("bank_pingan", -9800)
    ok, conf, _ = can_match(primary, shadow, "8223", "8223", "平安银行", "平安银行")
    assert not ok


def test_date_within_window():
    primary = raw("wechat", -9900, date_=datetime(2026, 4, 15))
    shadow = raw("bank_pingan", -9900, date_=datetime(2026, 4, 17))
    ok, conf, _ = can_match(primary, shadow, "8223", "8223", "平安银行", "平安银行")
    assert ok
    assert conf == 0.85


def test_date_outside_window():
    primary = raw("wechat", -9900, date_=datetime(2026, 4, 15))
    shadow = raw("bank_pingan", -9900, date_=datetime(2026, 4, 18))
    ok, _, _ = can_match(primary, shadow, "8223", "8223", "平安银行", "平安银行")
    assert not ok


def test_card_mismatch():
    primary = raw("wechat", -9900)
    shadow = raw("bank_pingan", -9900)
    ok, _, _ = can_match(primary, shadow, "8223", "1234", "平安银行", "平安银行")
    assert not ok


def test_is_shadow_wechat():
    r = raw("bank_pingan")
    r = r.model_copy(update={"counterparty": "财付通", "description": "消费"})
    assert is_app_shadow_in_bank(r) == "wechat"


def test_is_shadow_alipay():
    r = raw("bank_icbc")
    r = r.model_copy(update={"counterparty": "支付宝", "description": "消费"})
    assert is_app_shadow_in_bank(r) == "alipay"


def test_not_shadow_for_app_source():
    r = raw("wechat")
    r = r.model_copy(update={"counterparty": "财付通"})
    assert is_app_shadow_in_bank(r) is None
