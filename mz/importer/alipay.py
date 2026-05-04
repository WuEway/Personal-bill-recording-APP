from __future__ import annotations

import csv
import io
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from mz.importer.base import BaseImporter
from mz.models.transaction import RawTransactionDraft
from mz.utils.encoding import open_csv_auto

ALIPAY_HEADER_FIELDS = ("交易时间", "交易分类", "交易对方", "对方账号", "商品说明",
                         "收/支", "金额", "收/付款方式", "交易状态", "交易订单号",
                         "商家订单号", "备注")


class AlipayCsvImporter(BaseImporter):
    SOURCE_NAME = "alipay"
    DISPLAY_NAME = "支付宝交易明细"
    SUPPORTED_FORMATS = ["csv"]

    def detect(self, file_path: Path, file_format: str) -> bool:
        if file_format != "csv":
            return False
        try:
            content, _ = open_csv_auto(file_path)
            return "支付宝" in content[:3000] and "交易时间" in content[:3000]
        except Exception:
            return False

    def parse(self, file_path: Path, file_format: str) -> Iterator[RawTransactionDraft]:
        content, _ = open_csv_auto(file_path)
        lines = content.splitlines()

        header_idx = None
        for i, line in enumerate(lines):
            stripped = line.strip().lstrip("﻿")
            if stripped.startswith("交易时间,") or stripped.startswith("交易时间\t"):
                header_idx = i
                break
        if header_idx is None:
            return

        reader = csv.reader(lines[header_idx + 1:])
        for row in reader:
            if not row or not row[0].strip():
                continue
            draft = self._parse_row(row)
            if draft:
                yield draft

    def detect_period(self, file_path: Path, file_format: str) -> tuple[date, date]:
        dates: list[date] = []
        for draft in self.parse(file_path, file_format):
            dates.append(draft.txn_time.date())
        if not dates:
            today = date.today()
            return today, today
        return min(dates), max(dates)

    def _parse_row(self, row: list[str]) -> RawTransactionDraft | None:
        try:
            if len(row) < 12:
                return None
            time_str = row[0].strip()
            category = row[1].strip()
            party = row[2].strip()
            # row[3] = 对方账号 (skip)
            item = row[4].strip()
            sign_str = row[5].strip()
            amount_str = row[6].strip().replace(",", "")
            payment = row[7].strip()
            status = row[8].strip()
            txn_id = row[9].strip().rstrip("\t").strip()
            merchant_id = row[10].strip().rstrip("\t").strip()
            note = row[11].strip() if len(row) > 11 else ""

            # Skip header if repeated
            if time_str in ("交易时间", ""):
                return None

            # Skip zero-amount rows (医保支付 ¥0.00 等)
            try:
                amount = float(amount_str)
            except ValueError:
                return None

            if amount == 0.0:
                # treat as internal transfer
                return RawTransactionDraft(
                    source="alipay",
                    txn_time=self._parse_time(time_str),
                    amount_cents=0,
                    counterparty=party or None,
                    description=item or None,
                    payment_method_raw=None,
                    txn_type_raw=category or None,
                    direction="transfer",
                    external_txn_id=txn_id or None,
                    external_merchant_id=merchant_id or None,
                    is_group_payment=False,
                    raw_json={"raw_row": row[:12]},
                )

            if sign_str == "支出":
                direction = "expense"
                amount_cents = -int(round(abs(amount) * 100))
            elif sign_str == "收入":
                direction = "income"
                amount_cents = int(round(abs(amount) * 100))
            else:  # 不计收支
                direction = "transfer"
                amount_cents = int(round(amount * 100))

            # Split mixed payment (e.g. "工商银行储蓄卡(6930)&红包")
            primary_payment = payment.split("&")[0].strip() if payment else None

            return RawTransactionDraft(
                source="alipay",
                txn_time=self._parse_time(time_str),
                amount_cents=amount_cents,
                counterparty=party or None,
                description=item or None,
                payment_method_raw=primary_payment,
                txn_type_raw=category or None,
                direction=direction,
                external_txn_id=txn_id or None,
                external_merchant_id=merchant_id or None,
                is_group_payment=False,
                raw_json={"full_payment": payment, "note": note, "status": status},
            )
        except Exception:
            return None

    @staticmethod
    def _parse_time(s: str) -> datetime:
        for fmt in ("%Y-%m-%d %H:%M:%S", "%Y/%m/%d %H:%M:%S", "%Y-%m-%d"):
            try:
                return datetime.strptime(s, fmt)
            except ValueError:
                continue
        raise ValueError(f"无法解析时间: {s!r}")
