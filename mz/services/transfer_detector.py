from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

from mz.models.transaction import RawTransaction


@dataclass
class TransferRule:
    name: str
    matcher: Callable[[RawTransaction], bool]
    reason: str


BASE_RULES: list[TransferRule] = [
    TransferRule(
        "cc_repayment",
        lambda t: (
            (t.txn_type_raw and "信用卡还款" in t.txn_type_raw)
            or (
                t.counterparty and "信用卡" in t.counterparty
                and t.description and "还款" in t.description
            )
        ),
        "cc_repayment",
    ),
    # 美团月付还款：不识别为内部转账。
    # 美团月付是先消费后还款的赊账服务，消费明细在美团平台，不在 WeChat/Alipay 账单里，
    # 账单系统无法看到原始消费记录，因此还款本身就是本月真实支出，应该计入总支出。
    TransferRule(
        "huabei_repay",
        lambda t: (
            t.counterparty and "花呗" in t.counterparty
            and t.description and "还款" in t.description
        ),
        "huabei_repayment",
    ),
    TransferRule(
        "yuebao_in",
        lambda t: t.counterparty == "余额宝" and t.amount_cents < 0,
        "yuebao_purchase",
    ),
    TransferRule(
        "yuebao_out",
        lambda t: "余额宝" in (t.description or "") and t.amount_cents > 0,
        "yuebao_redeem",
    ),
    TransferRule(
        "lqt_in",
        lambda t: "零钱通" in (t.counterparty or "") and t.amount_cents < 0,
        "lqt_purchase",
    ),
    TransferRule(
        "lqt_out",
        lambda t: "零钱通" in (t.description or "") and t.amount_cents > 0,
        "lqt_redeem",
    ),
    TransferRule(
        "topup",
        lambda t: t.txn_type_raw and (
            "充值" in t.txn_type_raw or "储蓄卡入账" in t.txn_type_raw
        ),
        "topup",
    ),
    TransferRule(
        "withdrawal",
        lambda t: t.txn_type_raw and "提现" in t.txn_type_raw,
        "withdrawal",
    ),
    # 投资理财 → internal
    TransferRule(
        "investment",
        lambda t: t.txn_type_raw and any(
            kw in t.txn_type_raw for kw in ("基金", "理财", "股票", "债券", "定期")
        ),
        "investment",
    ),
    # Direction='transfer' from source → unknown internal transfer
    TransferRule(
        "source_transfer",
        lambda t: t.direction == "transfer",
        "unknown_transfer",
    ),
]


class TransferDetector:
    def __init__(self, user_name: str | None = None):
        self.rules = list(BASE_RULES)
        if user_name:
            self.rules.insert(
                0,
                TransferRule(
                    "self_transfer",
                    lambda t: t.counterparty == user_name,
                    "self_transfer",
                ),
            )

    def detect(self, txn: RawTransaction) -> str | None:
        """Return transfer reason or None if not internal transfer."""
        for rule in self.rules:
            try:
                if rule.matcher(txn):
                    return rule.reason
            except Exception:
                continue
        return None
