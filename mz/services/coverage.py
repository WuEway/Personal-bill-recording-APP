from __future__ import annotations

import sqlite3
from datetime import date

from mz.models.report import MissingAccount
from mz.repositories.account_repo import AccountRepository
from mz.repositories.raw_txn_repo import RawTransactionRepository
from mz.services.dedupe.matcher import INSTITUTION_TO_BANK_SOURCE

BANK_SOURCE_TO_INSTITUTION: dict[str, str] = {v: k for k, v in INSTITUTION_TO_BANK_SOURCE.items()}


class CoverageDetector:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.raw_repo = RawTransactionRepository(conn)
        self.acc_repo = AccountRepository(conn)

    def detect(self, period_start: date, period_end: date) -> list[MissingAccount]:
        all_raws = self.raw_repo.list_in_period(period_start, period_end)

        # 1. Bank-card accounts referenced in app (WeChat/Alipay) transactions
        referenced: dict[tuple[str, str, str], list[str]] = {}
        for raw in all_raws:
            if raw.payment_account_id:
                acc = self.acc_repo.get_by_id(raw.payment_account_id)
                if acc and acc.type in ("bank_debit", "bank_credit") and acc.last_4:
                    key = (acc.institution or "", acc.last_4, acc.type)
                    referenced.setdefault(key, []).append(raw.source)

        # 2. Institutions covered = any bank source has records in the period.
        #    We use source name → institution mapping (bank_pingan → 平安银行, etc.).
        #    This correctly handles the case where bank records don't carry their own
        #    account number in payment_account_id.
        covered_institutions: set[str] = set()
        for raw in all_raws:
            if raw.source.startswith("bank_"):
                inst = BANK_SOURCE_TO_INSTITUTION.get(raw.source)
                if inst:
                    covered_institutions.add(inst)

        # 3. Missing = referenced institution has no imported bank file
        result: list[MissingAccount] = []
        seen_institutions: set[str] = set()
        for (inst, last_4, acc_type), sources in referenced.items():
            if inst in covered_institutions:
                continue
            if inst in seen_institutions:
                continue
            seen_institutions.add(inst)
            source_counts: dict[str, int] = {}
            for s in sources:
                source_counts[s] = source_counts.get(s, 0) + 1
            evidence = [f"{src} 账单中出现 {cnt} 次" for src, cnt in source_counts.items()]
            result.append(
                MissingAccount(
                    institution=inst,
                    last_4=last_4,
                    type=acc_type,
                    evidence=evidence,
                    priority="high" if sum(source_counts.values()) >= 5 else "medium",
                )
            )

        # 4. Orphan shadows: bank records whose description mentions 财付通/支付宝
        #    but have no dedup_link — means we couldn't match them to a WeChat/Alipay record.
        for app_source, keyword in (("wechat", "财付通"), ("alipay", "支付宝")):
            orphans = self._list_orphan_shadows(app_source, keyword, period_start, period_end)
            if orphans:
                sample = [
                    f"  {o['date']} {o['amount']:>10} {o['bank']}  {o['desc']}"
                    for o in orphans[:5]
                ]
                tail = (
                    [f"  …共 {len(orphans)} 笔，运行 [bold]mz list shadows[/bold] 查看全部"]
                    if len(orphans) > 5
                    else [f"  共 {len(orphans)} 笔，运行 [bold]mz list shadows[/bold] 查看详情"]
                )
                result.append(
                    MissingAccount(
                        institution=app_source,
                        last_4=None,
                        type=f"{app_source}_orphan",
                        evidence=sample + tail,
                        priority="medium",
                    )
                )

        return sorted(result, key=lambda x: (x.priority == "high"), reverse=True)

    # ── Shared SQL fragment ──────────────────────────────────────────────────
    # A bank record is a TRUE orphan shadow only when ALL three hold:
    #   1. Its description mentions 财付通/支付宝 (should have an App counterpart)
    #   2. It has no dedup_link  (never matched to an App canonical)
    #   3. It has no canonical transaction of its own (primary_raw_id)
    #      — if it does, it is already counted as a standalone expense and
    #        is NOT truly "lost" money; showing it as a warning is misleading.
    _ORPHAN_SQL = """
        SELECT r.id, r.txn_time, r.amount_cents, r.source,
               r.counterparty, r.description
        FROM raw_transactions r
        LEFT JOIN dedup_links d    ON d.raw_txn_id    = r.id
        LEFT JOIN transactions  t  ON t.primary_raw_id = r.id
        WHERE r.source LIKE 'bank_%'
          AND (r.counterparty LIKE ? OR r.description LIKE ?)
          AND r.txn_time >= ? AND r.txn_time <= ?
          AND d.id IS NULL   -- not a linked shadow
          AND t.id IS NULL   -- not a standalone canonical primary (already counted)
        ORDER BY r.txn_time
    """

    def _list_orphan_shadows(
        self,
        app_source: str,
        keyword: str,
        start: date,
        end: date,
    ) -> list[dict]:
        rows = self.conn.execute(
            self._ORPHAN_SQL,
            (f"%{keyword}%", f"%{keyword}%", start.isoformat(), end.isoformat() + "T23:59:59"),
        ).fetchall()

        result = []
        for row in rows:
            amt = abs(row["amount_cents"]) / 100
            desc = (row["counterparty"] or "") + " " + (row["description"] or "")
            result.append({
                "id": row["id"],
                "date": row["txn_time"][:10],
                "amount": f"¥{amt:,.2f}",
                "bank": row["source"],
                "desc": desc.strip()[:40],
            })
        return result

    def list_all_orphan_shadows(self, start: date, end: date) -> list[dict]:
        """Return truly orphan bank shadow records: unmatched AND not yet a standalone expense."""
        result = []
        for keyword in ("财付通", "支付宝"):
            rows = self.conn.execute(
                self._ORPHAN_SQL,
                (f"%{keyword}%", f"%{keyword}%", start.isoformat(), end.isoformat() + "T23:59:59"),
            ).fetchall()
            for row in rows:
                desc = (row["counterparty"] or "") + " " + (row["description"] or "")
                result.append({
                    "id": row["id"],
                    "date": row["txn_time"][:10],
                    "amount_cents": row["amount_cents"],
                    "bank_source": row["source"],
                    "desc": desc.strip(),
                })
        return result
