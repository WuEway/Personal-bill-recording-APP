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

# Keyword sets for each logical column — matched against the header row.
# Pingan PDF header: 序号No. | 交易日期Date | 交易金额Transaction Amount |
#                   余额Balance | 交易地点Trading Place | 摘要Remark |
#                   备注Notes | *交易对手信息*Counterparty Information
COLUMN_KEYWORDS: dict[str, list[str]] = {
    "date":         ["交易日期", "Date"],
    "amount":       ["交易金额", "Transaction Amount", "金额"],
    "balance":      ["余额", "Balance"],
    "location":     ["交易地点", "Trading Place"],
    "remark":       ["摘要", "Remark"],
    "notes":        ["备注", "Notes"],
    "counterparty": ["交易对手", "Counterparty"],
}


def _clean_cell(cell: str | None) -> str | None:
    if cell is None:
        return None
    cell = cell.strip()
    if len(cell) <= 3 and all(c in WATERMARK_CHARS or c.isspace() for c in cell):
        return ""
    # Remove isolated watermark letters (B/A/P) — PDF overlay artifacts
    cell = re.sub(r"(?<![A-Za-z一-鿿])[BAP](?![A-Za-z一-鿿])", "", cell)
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

    # ── Table parsing ─────────────────────────────────────────────────────────

    def _build_col_map(self, header_cells: list[str | None]) -> dict[str, int]:
        """
        Match each logical column name to its index using keyword lookup against
        the header row.  Returns an empty dict if no recognised columns are found.
        """
        col_map: dict[str, int] = {}
        for field, keywords in COLUMN_KEYWORDS.items():
            for idx, cell in enumerate(header_cells):
                if cell and any(kw in cell for kw in keywords):
                    col_map[field] = idx
                    break
        return col_map

    def _parse_table(self, table: list[list]) -> Iterator[RawTransactionDraft]:
        if not table:
            return
        col_map: dict[str, int] = {}
        header_found = False

        for raw_row in table:
            cells = [_clean_cell(str(c) if c is not None else None) for c in raw_row]

            if not header_found:
                row_text = " ".join(c or "" for c in cells)
                # Detect header row by presence of key Chinese column labels
                if "交易日期" in row_text or "交易金额" in row_text:
                    col_map = self._build_col_map(cells)
                    header_found = True
                continue  # always skip header row itself

            if not any(c for c in cells):
                continue

            draft = self._parse_data_row(cells, col_map)
            if draft:
                yield draft

    def _parse_data_row(
        self,
        cells: list[str | None],
        col_map: dict[str, int],
    ) -> RawTransactionDraft | None:
        """
        Extract a transaction from one data row using the column map built from
        the header.  Falls back to a lightweight heuristic scan if the column
        map is incomplete (e.g., pdfplumber merged a header across pages).
        """
        try:
            def get(field: str) -> str | None:
                idx = col_map.get(field)
                if idx is None or idx >= len(cells):
                    return None
                return cells[idx] or None

            date_str   = get("date")
            amount_str = get("amount")
            remark     = get("remark")
            notes      = get("notes")
            cpty_raw   = get("counterparty")

            # Fallback: if col_map didn't resolve date/amount, use heuristics
            if not date_str:
                for c in cells:
                    if c and re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", c):
                        date_str = c
                        break
            if not amount_str:
                # Look for a cell with explicit +/- sign (avoids serial numbers)
                for c in cells:
                    if c and re.match(r"^[+\-]\d[\d,]*\.?\d*$", c.replace(" ", "")):
                        amount_str = c
                        break

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

            # Extract account name from "公司名-账户名-账号" counterparty format
            counterparty: str | None = None
            if cpty_raw:
                parts = cpty_raw.split("-")
                counterparty = (parts[1].strip() if len(parts) >= 2 else cpty_raw) or None

            # Shadow detection (财付通/支付宝 appears in 备注 or 摘要)
            shadow_text = f"{notes or ''} {remark or ''}"
            is_shadow_wechat = "财付通" in shadow_text or "微信" in shadow_text
            is_shadow_alipay = "支付宝" in shadow_text or "蚂蚁" in shadow_text

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
                description=notes or remark,
                payment_method_raw=payment_raw,
                txn_type_raw=remark,
                direction=direction,
                external_txn_id=None,
                external_merchant_id=None,
                is_group_payment=False,
                raw_json={"cells": cells, "col_map": col_map},
            )
        except Exception:
            return None
