from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime

from mz.models.category import CategoryProgress


@dataclass
class ComputedTotal:
    total_expense_cents: int
    raw_expense_cents: int
    offset_income_cents: int
    excluded_count: int


@dataclass
class ReportRow:
    txn_id: int
    txn_time: datetime
    amount_cents: int
    counterparty: str | None
    description: str | None
    payment_account_name: str | None
    inclusion: str
    is_group_payment: bool
    in_total: bool
    direction: str
    source: str | None = None


@dataclass
class MissingAccount:
    institution: str
    last_4: str | None
    type: str
    evidence: list[str]
    priority: str  # 'high' | 'medium' | 'low'


@dataclass
class MonthlyReport:
    period: tuple[date, date]
    total_expense_cents: int
    raw_expense_cents: int
    offset_income_cents: int
    total_income_cents: int
    expense_branch: list[ReportRow] = field(default_factory=list)
    income_branch: list[ReportRow] = field(default_factory=list)
    group_payment_branch: list[ReportRow] = field(default_factory=list)
    category_progresses: list[CategoryProgress] = field(default_factory=list)
    missing_accounts: list[MissingAccount] = field(default_factory=list)
