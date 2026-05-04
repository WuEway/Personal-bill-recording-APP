from __future__ import annotations

import sqlite3
from datetime import date

from mz.models.report import MissingAccount
from mz.repositories.account_repo import AccountRepository
from mz.repositories.imported_file_repo import ImportedFileRepository
from mz.repositories.raw_txn_repo import RawTransactionRepository


class CoverageDetector:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.raw_repo = RawTransactionRepository(conn)
        self.acc_repo = AccountRepository(conn)
        self.file_repo = ImportedFileRepository(conn)

    def detect(self, period_start: date, period_end: date) -> list[MissingAccount]:
        # 1. Accounts referenced in raw transactions (bank cards used via app payments)
        referenced: dict[tuple[str, str, str], list[str]] = {}
        for raw in self.raw_repo.list_in_period(period_start, period_end):
            if raw.payment_account_id:
                acc = self.acc_repo.get_by_id(raw.payment_account_id)
                if acc and acc.type in ("bank_debit", "bank_credit") and acc.last_4:
                    key = (acc.institution or "", acc.last_4, acc.type)
                    referenced.setdefault(key, []).append(raw.source)

        # 2. Accounts already covered by imported files
        covered: set[tuple[str, str, str]] = set()
        for raw in self.raw_repo.list_in_period(period_start, period_end):
            if raw.source.startswith("bank_") and raw.payment_account_id:
                acc = self.acc_repo.get_by_id(raw.payment_account_id)
                if acc and acc.last_4:
                    covered.add((acc.institution or "", acc.last_4, acc.type))

        # 3. Missing = referenced but not covered
        result: list[MissingAccount] = []
        for key, sources in referenced.items():
            if key not in covered:
                inst, last_4, acc_type = key
                evidence = [f"{src} 账单中出现 {len(sources)} 次" for src in set(sources)]
                result.append(
                    MissingAccount(
                        institution=inst,
                        last_4=last_4,
                        type=acc_type,
                        evidence=evidence,
                        priority="high" if len(sources) >= 5 else "medium",
                    )
                )

        # 4. Check for high orphan shadow rate
        for app_source in ("wechat", "alipay"):
            orphan_pct = self._orphan_shadow_pct(app_source, period_start, period_end)
            if orphan_pct > 0.3:
                result.append(
                    MissingAccount(
                        institution=app_source,
                        last_4=None,
                        type=f"{app_source}_balance",
                        evidence=[
                            f"银行流水中有大量 {app_source} 影子记录但未匹配到对应 App 账单"
                        ],
                        priority="high",
                    )
                )

        return sorted(result, key=lambda x: (x.priority == "high", len(x.evidence)), reverse=True)

    def _orphan_shadow_pct(self, app_source: str, start: date, end: date) -> float:
        """Fraction of bank rows with app shadow text that have no dedup link."""
        keyword = "财付通" if app_source == "wechat" else "支付宝"
        total = self.conn.execute(
            """SELECT COUNT(*) FROM raw_transactions
               WHERE source LIKE 'bank_%'
                 AND (counterparty LIKE ? OR description LIKE ?)
                 AND txn_time >= ? AND txn_time <= ?""",
            (f"%{keyword}%", f"%{keyword}%", start.isoformat(), end.isoformat() + "T23:59:59"),
        ).fetchone()[0]
        if total == 0:
            return 0.0
        linked = self.conn.execute(
            """SELECT COUNT(DISTINCT r.id) FROM raw_transactions r
               JOIN dedup_links d ON d.raw_txn_id = r.id
               WHERE r.source LIKE 'bank_%'
                 AND (r.counterparty LIKE ? OR r.description LIKE ?)
                 AND r.txn_time >= ? AND r.txn_time <= ?""",
            (f"%{keyword}%", f"%{keyword}%", start.isoformat(), end.isoformat() + "T23:59:59"),
        ).fetchone()[0]
        return (total - linked) / total
