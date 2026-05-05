from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from mz.models.transaction import RawTransaction, Transaction
from mz.repositories.account_repo import AccountRepository
from mz.repositories.raw_txn_repo import RawTransactionRepository
from mz.repositories.transaction_repo import TransactionRepository
from mz.services.dedupe.matcher import (
    can_match,
    institution_to_bank_source,
    is_app_shadow_in_bank,
)

BANK_SOURCES = ("bank_pingan", "bank_icbc", "bank_ccb", "bank_boc",
                "bank_abc", "bank_cmb", "bank_bocm", "bank_ceb",
                "bank_cmbc", "bank_spdb", "bank_cib")


class DedupeEngine:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.raw_repo = RawTransactionRepository(conn)
        self.txn_repo = TransactionRepository(conn)
        self.acc_repo = AccountRepository(conn)

    def run(self, period_start: date, period_end: date) -> dict[str, int]:
        """
        1. Create canonical transactions for all non-transfer app records.
        2. Match bank records to app canonical transactions (bidirectional):
           - App-driven: WeChat/Alipay paid via bank card X → find bank X record
             with same amount + date (ignoring time — bank records often only have date).
           - Text-driven: bank record says "财付通"/"支付宝" → find app record.
        3. Unmatched bank records become standalone canonical transactions.
        """
        expanded_start = period_start - timedelta(days=3)
        expanded_end = period_end + timedelta(days=3)

        # ── Step 1: canonical transactions for app records ───────────────────
        created = 0
        for raw in self.raw_repo.list_in_period(expanded_start, expanded_end):
            if raw.is_internal_transfer or raw.direction == "transfer":
                continue
            if raw.source.startswith("bank_"):
                continue
            if self.txn_repo.exists_for_raw(raw.id):
                continue
            self.txn_repo.create(self._make_txn(raw))
            created += 1

        # ── Step 2: build matching indexes over canonical app transactions ───
        app_txns = self.txn_repo.list_in_period(expanded_start, expanded_end)

        # Index A — app-driven (bidirectional):
        #   key = (bank_source, abs_amount_cents, date)
        #   value = list of canonical Transaction objects whose app record paid
        #           via a bank card from that bank
        bidir_index: dict[tuple[str, int, date], list[Transaction]] = {}
        for txn in app_txns:
            raw = self.raw_repo.get_by_id(txn.primary_raw_id)
            if not raw or not raw.payment_account_id:
                continue
            acc = self.acc_repo.get_by_id(raw.payment_account_id)
            if not acc or acc.type not in ("bank_debit", "bank_credit"):
                continue
            bank_src = institution_to_bank_source(acc.institution or "")
            if not bank_src:
                continue
            key = (bank_src, abs(txn.amount_cents), txn.txn_time.date())
            bidir_index.setdefault(key, []).append(txn)

        # Index B — text-driven (财付通/支付宝 in bank description):
        #   key = (abs_amount_cents, date)
        text_index: dict[tuple[int, date], list[Transaction]] = {}
        for txn in app_txns:
            key = (abs(txn.amount_cents), txn.txn_time.date())
            text_index.setdefault(key, []).append(txn)

        # ── Step 3: process bank records ─────────────────────────────────────
        bank_raws = [
            r
            for src in BANK_SOURCES
            for r in self.raw_repo.list_in_period(expanded_start, expanded_end, source=src)
            if not r.is_internal_transfer and r.direction != "transfer"
        ]

        linked = 0
        standalone = 0
        # Track canonical txn IDs already used as primary for a shadow link,
        # so we don't assign two bank records to the same canonical (1:1 mapping).
        used_canonical: set[int] = set()

        for bank_raw in bank_raws:
            matched = self._try_bidir_match(
                bank_raw, bidir_index, used_canonical
            )
            if not matched:
                matched = self._try_text_match(
                    bank_raw, text_index, used_canonical
                )

            if matched:
                linked += 1
            elif not self.txn_repo.exists_for_raw(bank_raw.id):
                self.txn_repo.create(self._make_txn(bank_raw))
                standalone += 1

        return {
            "created": created,
            "bank_linked_as_shadow": linked,
            "bank_standalone": standalone,
        }

    # ── Private helpers ──────────────────────────────────────────────────────

    def _try_bidir_match(
        self,
        bank_raw: RawTransaction,
        bidir_index: dict[tuple[str, int, date], list[Transaction]],
        used_canonical: set[int],
    ) -> bool:
        """
        App-driven bidirectional match:
        For each date in bank_raw.date ± 2 days, look for an app canonical
        transaction that paid via a card from the same bank (by source name),
        with the same amount.
        """
        for delta in range(3):
            for sign in ([0] if delta == 0 else [1, -1]):
                check_date = bank_raw.txn_time.date() + timedelta(days=delta * sign)
                key = (bank_raw.source, abs(bank_raw.amount_cents), check_date)
                for cand_txn in bidir_index.get(key, []):
                    if cand_txn.id in used_canonical:
                        continue
                    cand_raw = self.raw_repo.get_by_id(cand_txn.primary_raw_id)
                    if not cand_raw:
                        continue
                    ok, conf, reason = can_match(cand_raw, bank_raw)
                    if ok:
                        self._link(cand_txn, bank_raw, conf, reason + ",method=bidir")
                        used_canonical.add(cand_txn.id)
                        return True
        return False

    def _try_text_match(
        self,
        bank_raw: RawTransaction,
        text_index: dict[tuple[int, date], list[Transaction]],
        used_canonical: set[int],
    ) -> bool:
        """
        Text-driven match: bank record explicitly mentions 财付通/支付宝.
        """
        app_source = is_app_shadow_in_bank(bank_raw)
        if not app_source:
            return False

        for delta in range(3):
            for sign in ([0] if delta == 0 else [1, -1]):
                check_date = bank_raw.txn_time.date() + timedelta(days=delta * sign)
                key = (abs(bank_raw.amount_cents), check_date)
                for cand_txn in text_index.get(key, []):
                    if cand_txn.id in used_canonical:
                        continue
                    cand_raw = self.raw_repo.get_by_id(cand_txn.primary_raw_id)
                    if not cand_raw or cand_raw.source != app_source:
                        continue
                    ok, conf, reason = can_match(cand_raw, bank_raw)
                    if ok:
                        self._link(cand_txn, bank_raw, conf, reason + ",method=text")
                        used_canonical.add(cand_txn.id)
                        return True
        return False

    def _link(
        self,
        canonical_txn: Transaction,
        bank_raw: RawTransaction,
        confidence: float,
        reason: str,
    ) -> None:
        self.txn_repo.add_dedup_link(
            canonical_txn_id=canonical_txn.id,  # type: ignore[arg-type]
            raw_txn_id=bank_raw.id,
            confidence=confidence,
            reason=reason,
            method="exact",
        )
        self.raw_repo.mark_internal_transfer(
            bank_raw.id, f"shadow_of_txn_{canonical_txn.id}"
        )

    def _make_txn(self, raw: RawTransaction) -> Transaction:
        return Transaction(
            primary_raw_id=raw.id,
            txn_time=raw.txn_time,
            amount_cents=raw.amount_cents,
            counterparty=raw.counterparty,
            description=raw.description,
            payment_account_id=raw.payment_account_id,
            direction=raw.direction,  # type: ignore[arg-type]
            is_group_payment=raw.is_group_payment,
            inclusion="auto",
        )
