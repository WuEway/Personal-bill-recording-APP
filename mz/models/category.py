from __future__ import annotations

from datetime import datetime

from pydantic import BaseModel


class ManualCategory(BaseModel):
    id: int | None = None
    name: str
    icon: str | None = None
    monthly_budget_cents: int | None = None
    yearly_budget_cents: int | None = None
    is_active: bool = True
    created_at: datetime | None = None


class ManualEntry(BaseModel):
    id: int | None = None
    category_id: int
    txn_time: datetime
    amount_cents: int
    description: str | None = None
    linked_txn_id: int | None = None
    created_at: datetime | None = None


class CategoryProgress(BaseModel):
    category_id: int
    name: str
    icon: str
    month_spent_cents: int
    monthly_budget_cents: int | None
    monthly_pct: float | None
    year_spent_cents: int
    yearly_budget_cents: int | None
    yearly_pct: float | None
    alert_text: str
