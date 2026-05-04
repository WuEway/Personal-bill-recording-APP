from __future__ import annotations

import sqlite3
from datetime import date, timedelta

from mz.models.transaction import RawTransaction, Transaction
from mz.repositories.account_repo import AccountRepository
from mz.repositories.raw_txn_repo import RawTransactionRepository
from mz.repositories.transaction_repo import TransactionRepository
from mz.services.dedupe.matcher import can_match, is_app_shadow_in_bank


class DedupeEngine:
    def __init__(self, conn: sqlite3.Connection):
        self.conn = conn
        self.raw_repo = RawTransactionRepository(conn)
        self.txn_repo = TransactionRepository(conn)
        self.acc_repo = AccountRepository(conn)

    def run(self, period_start: date, period_end: date) -> dict[str, int]:
        """
        1. For every non-transfer, non-internal raw transaction, create a canonical transaction
           if one doesn't exist yet.
        2. Identify bank shadow rows and link them to the corresponding canonical transaction.

        Returns stats dict.
        """
        # Expand window for cross-period shadows
        expanded_start = period_start - timedelta(days=3)
        expanded_end = period_end + timedelta(days=3)

        # Step 1: create canonical transactions for all app transactions (wechat/alipay)
        created = 0
        for raw in self.raw_repo.list_in_period(expanded_start, expanded_end):
            if raw.is_internal_transfer:
                continue
            if raw.direction == "transfer":
                continue
            if raw.source.startswith("bank_"):
                continue  # handle bank rows in step 2
            if self.txn_repo.exists_for_raw(raw.id):
                continue

            txn = Transaction(
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
            self.txn_repo.create(txn)
            created += 1

        # Step 2: create canonical transactions for standalone bank rows (no matching app record)
        # and identify shadows
        linked = 0
        skipped_shadow = 0

        bank_raws = [
            r for source in ("bank_pingan", "bank_icbc", "bank_ccb")
            for r in self.raw_repo.list_in_period(expanded_start, expanded_end, source=source)
            if not r.is_internal_transfer and r.direction != "transfer"
        ]

        # Build app-transaction lookup: (amount_cents, date) → list of Transactions
        # within expanded window
        app_txns = self.txn_repo.list_in_period(expanded_start, expanded_end)
        app_index: dict[tuple[int, date], list[Transaction]] = {}
        for t in app_txns:
            key = (abs(t.amount_cents), t.txn_time.date())
            app_index.setdefault(key, []).append(t)

        for bank_raw in bank_raws:
            app_name = is_app_shadow_in_bank(bank_raw)
            matched = False

            if app_name:
                # Try to match against existing app canonical transactions
                bank_acc = (
                    self.acc_repo.get_by_id(bank_raw.payment_account_id)
                    if bank_raw.payment_account_id
                    else None
                )
                bank_last_4 = bank_acc.last_4 if bank_acc else None
                bank_institution = bank_acc.institution if bank_acc else None

                # Search candidates by amount + date window
                for delta in range(3):
                    for d_sign in (0, 1, -1):
                        cand_date = bank_raw.txn_time.date() + timedelta(days=delta * d_sign)
                        candidates = app_index.get((abs(bank_raw.amount_cents), cand_date), [])
                        for cand_txn in candidates:
                            cand_raw = self.raw_repo.get_by_id(cand_txn.primary_raw_id)
                            if not cand_raw:
                                continue
                            cand_acc = (
                                self.acc_repo.get_by_id(cand_raw.payment_account_id)
                                if cand_raw.payment_account_id
                                else None
                            )
                            ok, conf, reason = can_match(
                                primary=cand_raw,
                                shadow=bank_raw,
                                primary_last_4=cand_acc.last_4 if cand_acc else None,
                                shadow_account_last_4=bank_last_4,
                                primary_institution=cand_acc.institution if cand_acc else None,
                                shadow_institution=bank_institution,
                            )
                            if ok:
                                self.txn_repo.add_dedup_link(
                                    canonical_txn_id=cand_txn.id,  # type: ignore[arg-type]
                                    raw_txn_id=bank_raw.id,
                                    confidence=conf,
                                    reason=reason,
                                    method="exact",
                                )
                                # Mark bank row as internal transfer (shadow)
                                self.raw_repo.mark_internal_transfer(
                                    bank_raw.id, f"shadow_of_txn_{cand_txn.id}"
                                )
                                linked += 1
                                matched = True
                                break
                        if matched:
                            break
                    if matched:
                        break

            if not matched and not self.txn_repo.exists_for_raw(bank_raw.id):
                # Create standalone canonical transaction for this bank record
                txn = Transaction(
                    primary_raw_id=bank_raw.id,
                    txn_time=bank_raw.txn_time,
                    amount_cents=bank_raw.amount_cents,
                    counterparty=bank_raw.counterparty,
                    description=bank_raw.description,
                    payment_account_id=bank_raw.payment_account_id,
                    direction=bank_raw.direction,  # type: ignore[arg-type]
                    is_group_payment=bank_raw.is_group_payment,
                    inclusion="auto",
                )
                self.txn_repo.create(txn)
                skipped_shadow += 1

        return {
            "created": created,
            "bank_linked_as_shadow": linked,
            "bank_standalone": skipped_shadow,
        }
