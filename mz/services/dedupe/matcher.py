from __future__ import annotations

from datetime import date

from mz.models.transaction import RawTransaction

# Maps bank institution name → raw_transaction source name
INSTITUTION_TO_BANK_SOURCE: dict[str, str] = {
    "平安银行": "bank_pingan",
    "工商银行": "bank_icbc",
    "建设银行": "bank_ccb",
    "中国银行": "bank_boc",
    "农业银行": "bank_abc",
    "招商银行": "bank_cmb",
    "交通银行": "bank_bocm",
    "光大银行": "bank_ceb",
    "民生银行": "bank_cmbc",
    "浦发银行": "bank_spdb",
    "兴业银行": "bank_cib",
}


def institution_to_bank_source(institution: str) -> str | None:
    return INSTITUTION_TO_BANK_SOURCE.get(institution)


def is_app_shadow_in_bank(raw: RawTransaction) -> str | None:
    """If this bank record's description mentions WeChat/Alipay, return that app source name."""
    if not raw.source.startswith("bank_"):
        return None
    text = f"{raw.counterparty or ''} {raw.description or ''}"
    if "财付通" in text or "微信" in text:
        return "wechat"
    if "支付宝" in text or "蚂蚁" in text:
        return "alipay"
    return None


def can_match(
    primary: RawTransaction,
    shadow: RawTransaction,
    primary_last_4: str | None = None,
    shadow_account_last_4: str | None = None,
) -> tuple[bool, float, str]:
    """
    Return (matched, confidence, reason) for a primary (app) vs shadow (bank) pair.

    Checks: same absolute amount, both expense, date within ±2 days.
    Institution check is intentionally omitted here — it is enforced at the
    call site by restricting the candidate set to the right bank source.
    """
    if abs(primary.amount_cents) != abs(shadow.amount_cents):
        return False, 0.0, ""

    if primary.direction != "expense" or shadow.direction != "expense":
        return False, 0.0, ""

    # last_4 check only when both sides explicitly carry a card number
    if primary_last_4 and shadow_account_last_4:
        if primary_last_4 != shadow_account_last_4:
            return False, 0.0, ""

    # Bank records often lack time precision (stored as date 00:00:00),
    # so we tolerate a ±2-day window to cover settlement lag.
    delta = abs((primary.txn_time.date() - shadow.txn_time.date()).days)
    if delta > 2:
        return False, 0.0, ""

    confidence = {0: 1.0, 1: 0.95, 2: 0.85}[delta]
    reason = (
        f"amount={abs(primary.amount_cents) / 100:.2f},"
        f"last4={primary_last_4},"
        f"date_delta={delta}d"
    )
    return True, confidence, reason
