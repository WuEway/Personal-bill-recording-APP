from __future__ import annotations

import sqlite3
from datetime import date

from mz.models.report import MonthlyReport, ReportRow
from mz.repositories.account_repo import AccountRepository
from mz.repositories.transaction_repo import TransactionRepository
from mz.services.category_service import ManualCategoryService
from mz.services.coverage import CoverageDetector
from mz.services.inclusion import InclusionManager


class Reporter:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.txn_repo = TransactionRepository(conn)
        self.acc_repo = AccountRepository(conn)
        self.inclusion_mgr = InclusionManager(conn)
        self.cat_service = ManualCategoryService(conn)
        self.coverage = CoverageDetector(conn)

    def build_report(self, period_start: date, period_end: date) -> MonthlyReport:
        totals = self.inclusion_mgr.compute_total(period_start, period_end)

        expense_rows = []
        income_rows = []
        group_rows = []
        total_income = 0

        all_txns = self.txn_repo.list_in_period(period_start, period_end)
        for txn in all_txns:
            acc = self.acc_repo.get_by_id(txn.payment_account_id) if txn.payment_account_id else None
            acc_name = acc.name if acc else None

            # Source from raw
            raw_source = self.conn.execute(
                "SELECT source FROM raw_transactions WHERE id=?", (txn.primary_raw_id,)
            ).fetchone()
            source_str = raw_source[0] if raw_source else None

            effective = InclusionManager._effective(txn)
            in_total = effective in ("expense", "offset")

            row = ReportRow(
                txn_id=txn.id,  # type: ignore[arg-type]
                txn_time=txn.txn_time,
                amount_cents=abs(txn.amount_cents),
                counterparty=txn.counterparty,
                description=txn.description,
                payment_account_name=acc_name,
                inclusion=txn.inclusion,
                is_group_payment=txn.is_group_payment,
                in_total=in_total,
                direction=txn.direction,
                source=source_str,
            )

            if txn.is_group_payment:
                group_rows.append(row)
            elif txn.direction == "expense":
                expense_rows.append(row)
            elif txn.direction == "income":
                income_rows.append(row)
                total_income += abs(txn.amount_cents)

        cat_progresses = self.cat_service.get_all_progress()
        missing_accounts = self.coverage.detect(period_start, period_end)

        return MonthlyReport(
            period=(period_start, period_end),
            total_expense_cents=totals.total_expense_cents,
            raw_expense_cents=totals.raw_expense_cents,
            offset_income_cents=totals.offset_income_cents,
            total_income_cents=total_income,
            expense_branch=expense_rows,
            income_branch=income_rows,
            group_payment_branch=group_rows,
            category_progresses=cat_progresses,
            missing_accounts=missing_accounts,
        )
