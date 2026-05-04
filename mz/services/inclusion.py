from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from datetime import date

from mz.models.report import ComputedTotal
from mz.models.transaction import InclusionState, Transaction
from mz.repositories.transaction_repo import TransactionRepository


class InclusionManager:
    def __init__(self, conn: sqlite3.Connection):
        self.repo = TransactionRepository(conn)

    def set(self, txn_id: int, state: InclusionState, note: str = "") -> None:
        txn = self.repo.get_by_id(txn_id)
        if txn is None:
            raise ValueError(f"Transaction {txn_id} not found")
        if state == "offset" and txn.direction != "income":
            raise ValueError("'offset' 只能设置在收入交易上")
        self.repo.update_inclusion(txn_id, state, note)

    def reset(self, txn_id: int) -> None:
        self.set(txn_id, "auto")

    def bulk_set(self, txn_ids: list[int], state: InclusionState) -> None:
        for tid in txn_ids:
            self.set(tid, state)

    def compute_total(self, period_start: date, period_end: date) -> ComputedTotal:
        txns = self.repo.list_in_period(period_start, period_end)
        expense_sum = 0
        income_offset_sum = 0
        excluded_count = 0

        for t in txns:
            counted_in = self._effective(t)
            if counted_in == "expense":
                expense_sum += abs(t.amount_cents)
            elif counted_in == "offset":
                income_offset_sum += abs(t.amount_cents)
            elif counted_in == "excluded":
                excluded_count += 1

        return ComputedTotal(
            total_expense_cents=expense_sum - income_offset_sum,
            raw_expense_cents=expense_sum,
            offset_income_cents=income_offset_sum,
            excluded_count=excluded_count,
        )

    @staticmethod
    def _effective(t: Transaction) -> str:
        if t.inclusion == "excluded":
            return "excluded"
        if t.inclusion == "offset" and t.direction == "income":
            return "offset"
        if t.inclusion == "included":
            return "expense" if t.direction == "expense" else "excluded"
        # auto rules:
        if t.direction == "expense" and not t.is_group_payment:
            return "expense"
        return "excluded"  # group_payment / income default
