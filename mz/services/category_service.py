from __future__ import annotations

import sqlite3
from datetime import date, datetime

from mz.models.category import CategoryProgress, ManualCategory, ManualEntry
from mz.repositories.category_repo import CategoryRepository
from mz.repositories.transaction_repo import TransactionRepository
from mz.utils.text import fmt_amount, fmt_pct

DEFAULT_CATEGORY_POOL = [
    ("恋爱", "💑"),
    ("衣服", "👕"),
    ("培训学习", "📚"),
    ("旅游", "✈️"),
    ("医疗", "🏥"),
    ("数码", "📱"),
    ("宠物", "🐱"),
    ("健身美容", "💪"),
    ("演唱会·追星", "🎤"),
    ("游戏氪金", "🎮"),
    ("手办收藏", "🎎"),
    ("人情往来", "🎁"),
    ("朋友聚餐", "🍻"),
]


class ManualCategoryService:
    def __init__(self, conn: sqlite3.Connection):
        self.repo = CategoryRepository(conn)
        self.txn_repo = TransactionRepository(conn)

    def add_category(
        self,
        name: str,
        icon: str | None = None,
        monthly_budget: float | None = None,
        yearly_budget: float | None = None,
    ) -> int:
        existing = self.repo.get_category_by_name(name)
        if existing:
            raise ValueError(f"类目 '{name}' 已存在")
        cat = ManualCategory(
            name=name,
            icon=icon or "",
            monthly_budget_cents=int(monthly_budget * 100) if monthly_budget else None,
            yearly_budget_cents=int(yearly_budget * 100) if yearly_budget else None,
        )
        return self.repo.create_category(cat)

    def list_categories(self) -> list[ManualCategory]:
        return self.repo.list_categories()

    def remove_category(self, name: str) -> None:
        cat = self.repo.get_category_by_name(name)
        if not cat:
            raise ValueError(f"类目 '{name}' 不存在")
        self.repo.deactivate_category(cat.id)  # type: ignore[arg-type]

    def set_budget(
        self,
        name: str,
        monthly: float | None = None,
        yearly: float | None = None,
    ) -> None:
        cat = self.repo.get_category_by_name(name)
        if not cat:
            raise ValueError(f"类目 '{name}' 不存在")
        self.repo.update_budget(
            cat.id,  # type: ignore[arg-type]
            int(monthly * 100) if monthly is not None else None,
            int(yearly * 100) if yearly is not None else None,
        )

    def add_entry(
        self,
        category_name: str,
        amount: float,
        description: str,
        txn_time: datetime,
        linked_txn_id: int | None = None,
    ) -> int:
        cat = self.repo.get_category_by_name(category_name)
        if not cat:
            raise ValueError(f"类目 '{category_name}' 不存在")
        entry = ManualEntry(
            category_id=cat.id,  # type: ignore[arg-type]
            txn_time=txn_time,
            amount_cents=int(amount * 100),
            description=description,
            linked_txn_id=linked_txn_id,
        )
        entry_id = self.repo.create_entry(entry)
        if linked_txn_id:
            self.txn_repo.update_category(linked_txn_id, cat.id)
        return entry_id

    def get_progress(
        self, category_name: str, ref_time: datetime | None = None
    ) -> CategoryProgress:
        cat = self.repo.get_category_by_name(category_name)
        if not cat:
            raise ValueError(f"类目 '{category_name}' 不存在")
        if ref_time is None:
            ref_time = datetime.now()

        # Month range
        month_start = date(ref_time.year, ref_time.month, 1)
        if ref_time.month == 12:
            month_end = date(ref_time.year + 1, 1, 1)
        else:
            month_end = date(ref_time.year, ref_time.month + 1, 1)

        # Year range
        year_start = date(ref_time.year, 1, 1)
        year_end = date(ref_time.year, 12, 31)

        month_cents = self.repo.sum_entries_in_period(cat.id, month_start, month_end)  # type: ignore[arg-type]
        year_cents = self.repo.sum_entries_in_period(cat.id, year_start, year_end)  # type: ignore[arg-type]

        monthly_pct = (month_cents / cat.monthly_budget_cents) if cat.monthly_budget_cents else None
        yearly_pct = (year_cents / cat.yearly_budget_cents) if cat.yearly_budget_cents else None

        alert = self._make_alert(cat, month_cents, year_cents, monthly_pct, yearly_pct)

        return CategoryProgress(
            category_id=cat.id,  # type: ignore[arg-type]
            name=cat.name,
            icon=cat.icon or "",
            month_spent_cents=month_cents,
            monthly_budget_cents=cat.monthly_budget_cents,
            monthly_pct=monthly_pct,
            year_spent_cents=year_cents,
            yearly_budget_cents=cat.yearly_budget_cents,
            yearly_pct=yearly_pct,
            alert_text=alert,
        )

    def get_all_progress(self, ref_time: datetime | None = None) -> list[CategoryProgress]:
        return [self.get_progress(cat.name, ref_time) for cat in self.list_categories()]

    @staticmethod
    def _make_alert(
        cat: ManualCategory,
        month_cents: int,
        year_cents: int,
        monthly_pct: float | None,
        yearly_pct: float | None,
    ) -> str:
        parts = []
        if cat.monthly_budget_cents and monthly_pct is not None:
            if monthly_pct >= 1.0:
                parts.append(
                    f"⚠️ 本月{cat.name}已超 {(monthly_pct - 1) * 100:.0f}%"
                )
            elif monthly_pct >= 0.8:
                parts.append(
                    f"⚠️ 本月{cat.name}已用 {monthly_pct * 100:.0f}%"
                    f"（{fmt_amount(month_cents)}/{fmt_amount(cat.monthly_budget_cents)}）"
                )
            else:
                parts.append(
                    f"本月{cat.name} {fmt_amount(month_cents)}/{fmt_amount(cat.monthly_budget_cents)}"
                    f"（{monthly_pct * 100:.0f}%）"
                )
        if cat.yearly_budget_cents and yearly_pct is not None:
            parts.append(
                f"年度 {fmt_amount(year_cents)}/{fmt_amount(cat.yearly_budget_cents)}"
                f"（{yearly_pct * 100:.0f}%）"
            )
        return " · ".join(parts) if parts else f"{cat.name}: {fmt_amount(month_cents)}"
