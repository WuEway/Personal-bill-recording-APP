from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from mz.importer.base import BaseImporter
from mz.models.transaction import RawTransactionDraft
from mz.utils.text import collapse_chinese_repeats

WATERMARK_CHARS = set("BAP")
DATE_FMTS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y年%m月%d日")


def _clean_cell(cell: str | None) -> str | None:
    if cell is None:
        return None
    cell = cell.strip()
    # Entire cell is watermark-only (≤3 chars, all in BAP + whitespace)
    if len(cell) <= 3 and all(c in WATERMARK_CHARS or c.isspace() for c in cell):
        return ""
    # Remove isolated watermark letters (B/A/P) that appear as PDF overlay
    # artifacts. They are always single letters surrounded by whitespace or
    # at line boundaries — safe to strip without touching legitimate content.
    cell = re.sub(r"(?<![A-Za-z一-鿿])[BAP](?![A-Za-z一-鿿])", "", cell)
    # Collapse multiple spaces/newlines left by the removal above
    cell = re.sub(r"[ \t\n\r]+", " ", cell).strip()
    cell = collapse_chinese_repeats(cell)
    return cell


def _parse_amount(s: str) -> float | None:
    if not s:
        return None
    s = s.strip().replace(",", "").replace(" ", "")
    try:
        return float(s)
    except ValueError:
        return None


def _parse_date(s: str) -> datetime | None:
    if not s:
        return None
    s = s.strip()
    for fmt in DATE_FMTS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    # try partial datetime like "2026-04-01 12:00:00"
    m = re.search(r"(\d{4}[-/]\d{2}[-/]\d{2})", s)
    if m:
        ds = m.group(1).replace("/", "-")
        try:
            return datetime.strptime(ds, "%Y-%m-%d")
        except ValueError:
            pass
    return None


class PinganPdfImporter(BaseImporter):
    SOURCE_NAME = "bank_pingan"
    DISPLAY_NAME = "平安银行个人账户交易明细"
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
                return "平安银行" in text
        except Exception:
            return False

    def parse(self, file_path: Path, file_format: str) -> Iterator[RawTransactionDraft]:
        import pdfplumber

        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                tables = page.extract_tables(
                    table_settings={
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                    }
                )
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
            cells = [_clean_cell(str(c) if c is not None else None) for c in raw_row]
            # detect header row
            if not header_found:
                row_text = " ".join(c or "" for c in cells)
                if "交易日期" in row_text or "交易金额" in row_text:
                    header_found = True
                continue
            if not any(c for c in cells):
                continue
            draft = self._parse_data_row(cells)
            if draft:
                yield draft

    def _parse_data_row(self, cells: list[str | None]) -> RawTransactionDraft | None:
        try:
            # Typical columns: 序号, 交易日期, 交易金额, 余额, 交易地点, 摘要, 备注, 交易对手信息
            # Filter out empty strings to find real data
            non_empty = [c for c in cells if c]
            if len(non_empty) < 3:
                return None

            # Try to identify date column
            date_str = None
            amount_str = None
            remark = None
            counterparty = None

            for i, cell in enumerate(cells):
                if not cell:
                    continue
                # Date column
                if re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", cell) and date_str is None:
                    date_str = cell
                # Amount column (has +/- prefix or is numeric)
                elif re.match(r"^[+\-]?\d[\d,]*\.?\d*$", cell.replace(" ", "")) and amount_str is None:
                    amount_str = cell
                # Remark / counterparty
                elif len(cell) > 1 and not re.match(r"^\d+$", cell):
                    if remark is None and i >= 4:
                        remark = cell
                    elif counterparty is None and i >= 6:
                        counterparty = cell

            if not date_str or not amount_str:
                return None

            txn_time = _parse_date(date_str)
            if txn_time is None:
                return None

            amount = _parse_amount(amount_str)
            if amount is None:
                return None

            direction = "income" if amount > 0 else "expense"
            amount_cents = int(round(amount * 100))

            text = f"{remark or ''} {counterparty or ''}"
            is_shadow_wechat = "财付通" in text or "微信" in text
            is_shadow_alipay = "支付宝" in text or "蚂蚁" in text

            # 财付通/支付宝 bank entries are outgoing payments (WeChat/Alipay debits),
            # even when the PDF shows the amount as positive. Force expense direction
            # so the dedup engine can match them against app records.
            if (is_shadow_wechat or is_shadow_alipay) and direction == "income":
                direction = "expense"
                amount_cents = -abs(amount_cents)

            payment_raw = (
                "__SHADOW_WECHAT__" if is_shadow_wechat
                else "__SHADOW_ALIPAY__" if is_shadow_alipay
                else None
            )

            return RawTransactionDraft(
                source="bank_pingan",
                txn_time=txn_time,
                amount_cents=amount_cents,
                counterparty=counterparty,
                description=remark,
                payment_method_raw=payment_raw,
                txn_type_raw=remark,
                direction=direction,
                external_txn_id=None,
                external_merchant_id=None,
                is_group_payment=False,
                raw_json={"cells": cells},
            )
        except Exception:
            return None
