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
            # Column order: 序号No. | 交易日期Date | 交易金额 | 余额 | 交易地点 | 摘要 | 备注 | 交易对手信息
            # The serial number (1, 2, 3…) has no sign and no decimal point.
            # Transaction amounts always carry an explicit +/- sign: +1893.92, -60.0.
            # Balance has no sign but has a decimal point.
            # We locate columns by scanning position-aware so the serial number
            # is never mistaken for an amount.

            non_empty = [c for c in cells if c]
            if len(non_empty) < 3:
                return None

            # Step 1: find date column index
            date_str = None
            date_idx = -1
            for i, cell in enumerate(cells):
                if cell and re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", cell):
                    date_str = cell
                    date_idx = i
                    break

            if date_str is None or date_idx < 0:
                return None

            # Step 2: after the date, find first cell with explicit +/- sign = amount
            amount_str = None
            amount_idx = -1
            for i in range(date_idx + 1, len(cells)):
                cell = cells[i]
                if cell and re.match(r"^[+\-]\d[\d,]*\.?\d*$", cell.replace(" ", "")):
                    amount_str = cell
                    amount_idx = i
                    break

            if amount_str is None:
                return None

            # Step 3: skip the next numeric cell (balance), then collect text cells in order
            # [交易地点, 摘要, 备注, 交易对手信息]
            text_cells: list[str] = []
            skip_next_numeric = True
            for i in range(amount_idx + 1, len(cells)):
                cell = cells[i]
                if not cell:
                    continue
                if skip_next_numeric and re.match(r"^\d[\d,]*\.?\d*$", cell.replace(" ", "")):
                    skip_next_numeric = False
                    continue
                skip_next_numeric = False
                text_cells.append(cell)

            # Map positional text cells to semantic columns
            location = text_cells[0] if len(text_cells) > 0 else None
            remark = text_cells[1] if len(text_cells) > 1 else None
            notes = text_cells[2] if len(text_cells) > 2 else None
            counterparty_raw = text_cells[3] if len(text_cells) > 3 else None

            # Extract account name from counterparty "公司名-账户名-账号" format
            counterparty = None
            if counterparty_raw:
                parts = counterparty_raw.split("-")
                if len(parts) >= 2:
                    counterparty = parts[1].strip() or counterparty_raw
                else:
                    counterparty = counterparty_raw

            txn_time = _parse_date(date_str)
            if txn_time is None:
                return None

            amount = _parse_amount(amount_str)
            if amount is None:
                return None

            direction = "income" if amount > 0 else "expense"
            amount_cents = int(round(amount * 100))

            # Shadow detection: 财付通 appears in 备注 (notes); 支付宝 may appear in remark/notes
            notes_text = notes or ""
            remark_text = remark or ""
            is_shadow_wechat = "财付通" in notes_text or "微信" in notes_text
            is_shadow_alipay = "支付宝" in notes_text or "蚂蚁" in notes_text or \
                               "支付宝" in remark_text or "蚂蚁" in remark_text

            payment_raw = (
                "__SHADOW_WECHAT__" if is_shadow_wechat
                else "__SHADOW_ALIPAY__" if is_shadow_alipay
                else None
            )

            description = remark or location

            return RawTransactionDraft(
                source="bank_pingan",
                txn_time=txn_time,
                amount_cents=amount_cents,
                counterparty=counterparty,
                description=description,
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
