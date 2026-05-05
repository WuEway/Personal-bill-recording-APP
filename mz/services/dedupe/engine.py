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
        Step 1  — Create canonical transactions for non-transfer app records.
        Step 1.5— Propagate internal-transfer status from app records to their
                  corresponding bank debits (e.g. 美团月付还款 in WeChat → the
                  matching Pingan debit should also be internal transfer).
                  This prevents the bank debit from becoming a phantom standalone
                  expense that causes double-counting on re-import.
        Step 2  — Match remaining bank records to app canonical transactions.
        Step 3  — Unmatched bank records become standalone canonical transactions.
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

        # ── Step 1.5: propagate internal transfers to bank shadows ───────────
        # If an app record is an internal transfer (e.g. credit repayment) AND
        # it paid via a bank card, the corresponding bank debit is also an
        # internal transfer.  Mark it now so Step 2/3 won't turn it into a
        # standalone expense canonical.
        all_raws = self.raw_repo.list_in_period(expanded_start, expanded_end)
        propagated = self._propagate_internal_transfers(all_raws, expanded_start, expanded_end)

        # ── Step 2: build matching indexes over canonical app transactions ───
        app_txns = self.txn_repo.list_in_period(expanded_start, expanded_end)

        # Index A — app-driven (bidirectional):
        #   key = (bank_source, abs_amount_cents, date)
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
        # Re-fetch bank raws after propagation so the newly-marked records are
        # excluded (is_internal_transfer=1 are filtered out below).
        bank_raws = [
            r
            for src in BANK_SOURCES
            for r in self.raw_repo.list_in_period(expanded_start, expanded_end, source=src)
            if not r.is_internal_transfer and r.direction != "transfer"
        ]

        linked = 0
        standalone = 0
        used_canonical: set[int] = set()

        for bank_raw in bank_raws:
            matched = self._try_bidir_match(bank_raw, bidir_index, used_canonical)
            if not matched:
                matched = self._try_text_match(bank_raw, text_index, used_canonical)

            if matched:
                linked += 1
            elif not self.txn_repo.exists_for_raw(bank_raw.id):
                self.txn_repo.create(self._make_txn(bank_raw))
                standalone += 1

        return {
            "created": created,
            "bank_linked_as_shadow": linked,
            "bank_standalone": standalone,
            "bank_internal_propagated": propagated,
        }

    # ── Private helpers ──────────────────────────────────────────────────────

    def _propagate_internal_transfers(
        self,
        all_raws: list[RawTransaction],
        expanded_start: date,
        expanded_end: date,
    ) -> int:
        """
        For every app internal-transfer record that paid via a bank card, find
        the matching bank debit (same institution + amount + date ±2 days) and
        mark it as internal transfer too.

        This prevents the bank-side record from becoming a phantom standalone
        expense canonical when the app-side record has no canonical to link to.

        Returns the count of bank records newly marked.
        """
        # Build index of app internal transfers: (bank_source, abs_cents, date) → raw
        internal_index: dict[tuple[str, int, date], list[RawTransaction]] = {}
        for r in all_raws:
            if not r.is_internal_transfer:
                continue
            if r.source.startswith("bank_"):
                continue
            if r.direction != "expense":
                continue
            if not r.payment_account_id:
                continue
            acc = self.acc_repo.get_by_id(r.payment_account_id)
            if not acc or acc.type not in ("bank_debit", "bank_credit"):
                continue
            bank_src = institution_to_bank_source(acc.institution or "")
            if not bank_src:
                continue
            key = (bank_src, abs(r.amount_cents), r.txn_time.date())
            internal_index.setdefault(key, []).append(r)

        if not internal_index:
            return 0

        count = 0
        for src in BANK_SOURCES:
            for bank_raw in self.raw_repo.list_in_period(
                expanded_start, expanded_end, source=src
            ):
                if bank_raw.is_internal_transfer:
                    continue
                if bank_raw.direction != "expense":
                    continue
                # Only consider bank records whose text suggests an app payment;
                # a plain POS debit with no 财付通 text is not an app shadow.
                if not is_app_shadow_in_bank(bank_raw):
                    continue

                for delta in range(3):
                    matched = False
                    for sign in ([0] if delta == 0 else [1, -1]):
                        check_date = bank_raw.txn_time.date() + timedelta(days=delta * sign)
                        key = (bank_raw.source, abs(bank_raw.amount_cents), check_date)
                        if internal_index.get(key):
                            app_raw = internal_index[key][0]
                            self.raw_repo.mark_internal_transfer(
                                bank_raw.id,
                                f"shadow_of_internal_raw_{app_raw.id}:{app_raw.transfer_reason}",
                            )
                            count += 1
                            matched = True
                            break
                    if matched:
                        break
        return count

    def _try_bidir_match(
        self,
        bank_raw: RawTransaction,
        bidir_index: dict[tuple[str, int, date], list[Transaction]],
        used_canonical: set[int],
    ) -> bool:
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
