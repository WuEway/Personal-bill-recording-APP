from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

AccountType = Literal[
    "bank_debit",
    "bank_credit",
    "wechat_balance",
    "alipay_balance",
    "huabei",
    "meituan_yuefu",
    "yuebao",
    "lingqiantong",
    "unknown",
]


class Account(BaseModel):
    id: int | None = None
    type: AccountType
    name: str
    institution: str | None = None
    last_4: str | None = None
    is_credit: bool = False
    is_active: bool = True
    created_at: datetime | None = None
