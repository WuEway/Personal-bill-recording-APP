from __future__ import annotations

from datetime import date, timedelta


def month_range(year_month: str) -> tuple[date, date]:
    """'2026-04' → (date(2026,4,1), date(2026,4,30))"""
    y, m = year_month.split("-")
    start = date(int(y), int(m), 1)
    # first day of next month minus one day
    if int(m) == 12:
        end = date(int(y) + 1, 1, 1) - timedelta(days=1)
    else:
        end = date(int(y), int(m) + 1, 1) - timedelta(days=1)
    return start, end


def current_month() -> str:
    from datetime import date as _date
    today = _date.today()
    return f"{today.year:04d}-{today.month:02d}"
