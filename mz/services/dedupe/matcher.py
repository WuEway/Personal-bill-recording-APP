from __future__ import annotations

from mz.models.transaction import RawTransaction


def is_app_shadow_in_bank(raw: RawTransaction) -> str | None:
    """If this bank transaction is a shadow of a WeChat/Alipay tx, return the app source name."""
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
    primary_last_4: str | None,
    shadow_account_last_4: str | None,
    primary_institution: str | None,
    shadow_institution: str | None,
) -> tuple[bool, float, str]:
    """
    Return (matched, confidence, reason) for a primary (app) vs shadow (bank) pair.
    """
    # Amounts must match (absolute value)
    if abs(primary.amount_cents) != abs(shadow.amount_cents):
        return False, 0.0, ""

    # Both must be expense
    if primary.direction != "expense" or shadow.direction != "expense":
        return False, 0.0, ""

    # Account match: last_4 + institution
    if primary_last_4 and shadow_account_last_4:
        if primary_last_4 != shadow_account_last_4:
            return False, 0.0, ""
    if primary_institution and shadow_institution:
        if primary_institution != shadow_institution:
            return False, 0.0, ""

    # Date window: ±2 days
    delta = abs((primary.txn_time.date() - shadow.txn_time.date()).days)
    if delta > 2:
        return False, 0.0, ""

    confidence = {0: 1.0, 1: 0.95, 2: 0.85}[delta]
    reason = (
        f"amount={abs(primary.amount_cents)/100:.2f},"
        f"last_4={primary_last_4},"
        f"date_delta={delta}d"
    )
    return True, confidence, reason
