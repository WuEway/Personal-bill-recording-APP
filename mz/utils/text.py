from __future__ import annotations

import re


def collapse_chinese_repeats(text: str) -> str:
    """Fold consecutive duplicate CJK characters (Ping An PDF watermark artifact)."""
    return re.sub(r"([一-鿿])\1+", r"\1", text)


def fmt_amount(cents: int) -> str:
    """Format integer cents as ¥X.XX string."""
    return f"¥{abs(cents) / 100:,.2f}"


def fmt_pct(pct: float | None) -> str:
    if pct is None:
        return "—"
    return f"{pct * 100:.0f}%"
