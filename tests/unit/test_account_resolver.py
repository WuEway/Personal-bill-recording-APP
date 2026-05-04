from __future__ import annotations

import pytest

from mz.repositories.account_repo import AccountRepository
from mz.services.account_resolver import AccountResolver


def test_resolve_wechat_balance(conn):
    resolver = AccountResolver(AccountRepository(conn))
    acc_id = resolver.resolve("零钱", "wechat")
    assert acc_id is not None
    acc = AccountRepository(conn).get_by_id(acc_id)
    assert acc.type == "wechat_balance"


def test_resolve_bank_card(conn):
    resolver = AccountResolver(AccountRepository(conn))
    acc_id = resolver.resolve("平安银行储蓄卡(8223)", "wechat")
    acc = AccountRepository(conn).get_by_id(acc_id)
    assert acc.type == "bank_debit"
    assert acc.last_4 == "8223"
    assert acc.institution == "平安银行"


def test_resolve_credit_card(conn):
    resolver = AccountResolver(AccountRepository(conn))
    acc_id = resolver.resolve("建设银行信用卡(3906)", "wechat")
    acc = AccountRepository(conn).get_by_id(acc_id)
    assert acc.type == "bank_credit"
    assert acc.is_credit is True
    assert acc.last_4 == "3906"


def test_resolve_yuebao(conn):
    resolver = AccountResolver(AccountRepository(conn))
    acc_id = resolver.resolve("余额宝", "alipay")
    acc = AccountRepository(conn).get_by_id(acc_id)
    assert acc.type == "yuebao"


def test_resolve_shadow_wechat(conn):
    resolver = AccountResolver(AccountRepository(conn))
    acc_id = resolver.resolve("__SHADOW_WECHAT__", "bank_pingan")
    acc = AccountRepository(conn).get_by_id(acc_id)
    assert acc.type == "wechat_balance"


def test_idempotent_creation(conn):
    """Same account created twice returns same id."""
    resolver = AccountResolver(AccountRepository(conn))
    id1 = resolver.resolve("平安银行储蓄卡(8223)", "wechat")
    id2 = resolver.resolve("平安银行储蓄卡(8223)", "alipay")
    assert id1 == id2
