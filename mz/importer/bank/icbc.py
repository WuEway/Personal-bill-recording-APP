from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from mz.importer.base import BaseImporter
from mz.models.transaction import RawTransactionDraft


class IcbcPdfImporter(BaseImporter):
    SOURCE_NAME = "bank_icbc"
    DISPLAY_NAME = "工商银行历史明细"
    SUPPORTED_FORMATS = ["pdf"]

    def detect(self, file_path: Path, file_format: str) -> bool:
        if file_format != "pdf":
            return False
        try:
            import pdfplumber

            with pdfplumber.open(file_path) as pdf:
                if not pdf.pages:
                    return False
                text = (pdf.pages[0].extract_text() or "")[:2000]
                return "工商银行" in text or "ICBC" in text
        except Exception:
            return False

    def parse(self, file_path: Path, file_format: str) -> Iterator[RawTransactionDraft]:
        import pdfplumber

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables()
                for table in tables:
                    yield from self._parse_table(table)

    def detect_period(self, file_path: Path, file_format: str) -> tuple[date, date]:
        dates: list[date] = []
        for draft in self.parse(file_path, file_format):
            dates.append(draft.txn_time.date())
        if not dates:
            today = date.today()
            return today, today
        return min(dates), max(dates)

    def _parse_table(self, table: list[list]) -> Iterator[RawTransactionDraft]:
        if not table:
            return
        header_found = False
        for raw_row in table:
            cells = [str(c).strip() if c else "" for c in raw_row]
            if not header_found:
                row_text = " ".join(cells)
                if "交易日期" in row_text or "摘要" in row_text:
                    header_found = True
                continue
            if not any(cells):
                continue
            draft = self._parse_data_row(cells)
            if draft:
                yield draft

    def _parse_data_row(self, cells: list[str]) -> RawTransactionDraft | None:
        try:
            # ICBC typical: 卡号, 交易日期/时间, 摘要, 收入金额, 支出金额, 余额, 对方户名, 备注
            non_empty = [c for c in cells if c]
            if len(non_empty) < 3:
                return None

            date_str = None
            income_str = None
            expense_str = None
            summary = None
            counterparty = None

            for i, cell in enumerate(cells):
                if not cell:
                    continue
                m_date = re.match(r"(\d{4}[-/]\d{2}[-/]\d{2})", cell)
                if m_date and date_str is None:
                    date_str = m_date.group(1)
                elif re.match(r"^\d[\d,]*\.\d{2}$", cell):
                    if income_str is None:
                        income_str = cell
                    elif expense_str is None:
                        expense_str = cell
                elif len(cell) > 1 and not re.match(r"^\d+$", cell):
                    if summary is None and i >= 2:
                        summary = cell
                    elif counterparty is None and i >= 5:
                        counterparty = cell

            if not date_str:
                return None

            txn_time = datetime.strptime(date_str.replace("/", "-"), "%Y-%m-%d")

            if income_str and float(income_str.replace(",", "")) > 0:
                amount = float(income_str.replace(",", ""))
                direction = "income"
                amount_cents = int(round(amount * 100))
            elif expense_str and float(expense_str.replace(",", "")) > 0:
                amount = float(expense_str.replace(",", ""))
                direction = "expense"
                amount_cents = -int(round(amount * 100))
            else:
                return None

            text = f"{summary or ''} {counterparty or ''}"
            is_shadow_wechat = "财付通" in text or "微信" in text
            is_shadow_alipay = "支付宝" in text or "蚂蚁" in text
            payment_raw = (
                "__SHADOW_WECHAT__" if is_shadow_wechat
                else "__SHADOW_ALIPAY__" if is_shadow_alipay
                else None
            )

            return RawTransactionDraft(
                source="bank_icbc",
                txn_time=txn_time,
                amount_cents=amount_cents,
                counterparty=counterparty,
                description=summary,
                payment_method_raw=payment_raw,
                txn_type_raw=summary,
                direction=direction,
                external_txn_id=None,
                external_merchant_id=None,
                is_group_payment=False,
                raw_json={"cells": cells},
            )
        except Exception:
            return None
