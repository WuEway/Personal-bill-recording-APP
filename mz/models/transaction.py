from __future__ import annotations

import json
from datetime import date, datetime
from typing import Any, Literal

from pydantic import BaseModel, field_validator

Direction = Literal["expense", "income", "transfer"]
InclusionState = Literal["auto", "included", "excluded", "offset"]


class RawTransactionDraft(BaseModel):
    """Parsed record before writing to DB; no ID yet."""
    source: str
    txn_time: datetime
    amount_cents: int
    currency: str = "CNY"
    counterparty: str | None = None
    description: str | None = None
    payment_method_raw: str | None = None
    txn_type_raw: str | None = None
    direction: Direction
    external_txn_id: str | None = None
    external_merchant_id: str | None = None
    is_group_payment: bool = False
    raw_json: dict[str, Any] = {}

    def raw_json_str(self) -> str:
        return json.dumps(self.raw_json, ensure_ascii=False, default=str)


class RawTransaction(BaseModel):
    """Row read back from raw_transactions table."""
    id: int
    source: str
    source_file_id: int
    txn_time: datetime
    amount_cents: int
    currency: str = "CNY"
    counterparty: str | None = None
    description: str | None = None
    payment_account_id: int | None = None
    txn_type_raw: str | None = None
    direction: Direction
    external_txn_id: str | None = None
    external_merchant_id: str | None = None
    raw_json: str = "{}"
    is_internal_transfer: bool = False
    transfer_reason: str | None = None
    is_group_payment: bool = False
    is_refund: bool = False


class Transaction(BaseModel):
    """Canonical (deduplicated) transaction."""
    id: int | None = None
    primary_raw_id: int
    txn_time: datetime
    amount_cents: int
    counterparty: str | None = None
    description: str | None = None
    payment_account_id: int | None = None
    direction: Literal["expense", "income"]
    is_group_payment: bool = False
    inclusion: InclusionState = "auto"
    inclusion_set_at: datetime | None = None
    inclusion_note: str | None = None
    manual_category_id: int | None = None
    manual_entry_id: int | None = None
    notes: str | None = None


class ImportedFile(BaseModel):
    id: int | None = None
    source: str
    file_path: str
    file_hash: str
    file_format: str
    is_encrypted: bool = False
    period_start: date | None = None
    period_end: date | None = None
    row_count: int = 0
    account_label: str | None = None  # e.g. "8223" for bank cards
    imported_at: datetime | None = None
