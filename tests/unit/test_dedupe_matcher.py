from __future__ import annotations

from datetime import datetime

from mz.models.transaction import RawTransaction
from mz.services.dedupe.matcher import can_match, is_app_shadow_in_bank, institution_to_bank_source


def raw(source="wechat", amount=-9900, direction="expense", date_=None):
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
    primary = raw("wechat", -9900, "expense", datetime(2026, 4, 15, 18, 31))
    shadow = raw("bank_pingan", -9900, "expense", datetime(2026, 4, 15))
    ok, conf, reason = can_match(primary, shadow)
    assert ok
    assert conf == 1.0


def test_bank_date_only_matches_app_with_time():
    # Core fix: bank records only have a date (00:00:00), app records have full timestamp.
    # They must be recognized as the same transaction.
    primary = raw("wechat", -15000, "expense", datetime(2026, 4, 24, 18, 31, 45))
    shadow = raw("bank_pingan", -15000, "expense", datetime(2026, 4, 24, 0, 0, 0))
    ok, conf, _ = can_match(primary, shadow)
    assert ok
    assert conf == 1.0


def test_amount_mismatch():
    primary = raw("wechat", -9900)
    shadow = raw("bank_pingan", -9800)
    ok, _, _ = can_match(primary, shadow)
    assert not ok


def test_date_within_window():
    primary = raw("wechat", -9900, date_=datetime(2026, 4, 15))
    shadow = raw("bank_pingan", -9900, date_=datetime(2026, 4, 17))
    ok, conf, _ = can_match(primary, shadow)
    assert ok
    assert conf == 0.85


def test_date_outside_window():
    primary = raw("wechat", -9900, date_=datetime(2026, 4, 15))
    shadow = raw("bank_pingan", -9900, date_=datetime(2026, 4, 18))
    ok, _, _ = can_match(primary, shadow)
    assert not ok


def test_card_mismatch_blocks_match():
    primary = raw("wechat", -9900)
    shadow = raw("bank_pingan", -9900)
    ok, _, _ = can_match(primary, shadow, primary_last_4="8223", shadow_account_last_4="1234")
    assert not ok


def test_no_last4_still_matches():
    # When last_4 is unknown on either side, match proceeds on amount + date alone.
    primary = raw("wechat", -9900)
    shadow = raw("bank_pingan", -9900)
    ok, _, _ = can_match(primary, shadow, primary_last_4="8223", shadow_account_last_4=None)
    assert ok


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


def test_institution_to_bank_source():
    assert institution_to_bank_source("平安银行") == "bank_pingan"
    assert institution_to_bank_source("工商银行") == "bank_icbc"
    assert institution_to_bank_source("未知银行") is None
