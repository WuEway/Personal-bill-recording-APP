from __future__ import annotations

import re
from datetime import date, datetime
from pathlib import Path
from typing import Iterator

from mz.importer.base import BaseImporter
from mz.models.transaction import RawTransactionDraft

# Column header keywords for header-driven mapping (same approach as Pingan)
COLUMN_KEYWORDS: dict[str, list[str]] = {
    "date":         ["交易日期", "记账日期", "Date"],
    "amount":       ["交易金额", "发生额", "Amount", "金额"],
    "balance":      ["余额", "Balance", "账户余额"],
    "summary":      ["摘要", "交易摘要", "Summary", "用途"],
    "counterparty": ["对方户名", "对方名称", "Counterparty", "交易对方"],
    "ref":          ["交易参考号", "参考号", "流水号"],
}

DATE_FMTS = ("%Y-%m-%d", "%Y/%m/%d", "%Y%m%d", "%Y年%m月%d日")

# ICBC PDFs overlay isolated single chars (digits, letters) as watermarks.
# Strip any character that appears alone between whitespace/newlines.
_WATERMARK_RE = re.compile(r"(?<![^\s])([A-Za-z0-9])(?![^\s])")


def _clean_cell(cell: str) -> str:
    """Remove isolated watermark characters from an ICBC PDF cell."""
    if not cell:
        return ""
    cell = _WATERMARK_RE.sub(" ", cell)
    return re.sub(r"\s+", " ", cell).strip()


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
        # col_map persists across pages: multi-page tables (no header on page 2+)
        # reuse the layout detected on page 1.
        col_map: dict[str, int] = {}
        with pdfplumber.open(file_path) as pdf:
            for page in pdf.pages:
                # Try line-based extraction first (clean bordered tables).
                # ICBC PDFs sometimes use text-alignment without drawn lines;
                # in that case fall back to the default "text" strategy which
                # yields more rows.
                tables_lines = page.extract_tables(
                    table_settings={
                        "vertical_strategy": "lines",
                        "horizontal_strategy": "lines",
                    }
                )
                tables_text = page.extract_tables()  # default text strategy

                # Use whichever strategy returns more total rows
                total_lines = sum(len(t) for t in tables_lines)
                total_text  = sum(len(t) for t in tables_text)
                tables = tables_lines if total_lines >= total_text else tables_text

                for table in tables:
                    for draft, updated_map in self._parse_table_stateful(table, col_map):
                        col_map = updated_map
                        yield draft

    def extract_account_label(self, file_path: Path, file_format: str) -> str | None:
        try:
            import pdfplumber
            with pdfplumber.open(file_path) as pdf:
                text = "".join(page.extract_text() or "" for page in pdf.pages[:2])
            for pattern in (
                r'账号[：:\s]+[\d\s*×·-]*?(\d{4})\b',
                r'卡号[：:\s]+[\d\s*×·-]*?(\d{4})\b',
                r'尾号\s*[：:\s]*(\d{4})',
                r'[*×·]{2,}\s*(\d{4})\b',
            ):
                m = re.search(pattern, text)
                if m:
                    return m.group(1)
        except Exception:
            pass
        return None

    def detect_period(self, file_path: Path, file_format: str) -> tuple[date, date]:
        dates: list[date] = []
        for draft in self.parse(file_path, file_format):
            dates.append(draft.txn_time.date())
        if not dates:
            today = date.today()
            return today, today
        return min(dates), max(dates)

    # ── Table parsing ─────────────────────────────────────────────────────────

    def _build_col_map(self, header_cells: list[str]) -> dict[str, int]:
        col_map: dict[str, int] = {}
        for field, keywords in COLUMN_KEYWORDS.items():
            for idx, cell in enumerate(header_cells):
                if cell and any(kw in cell for kw in keywords):
                    col_map[field] = idx
                    break
        return col_map

    def _parse_table_stateful(
        self,
        table: list[list],
        col_map: dict[str, int],
    ):
        """
        Parse one extracted table, yielding (draft, updated_col_map) pairs.
        col_map is passed in and updated when a header row is found, allowing
        multi-page tables to share the same column layout across pages.
        """
        if not table:
            return

        for raw_row in table:
            cells = [_clean_cell(str(c)) if c is not None else "" for c in raw_row]

            row_text = " ".join(cells)
            # Detect header row
            if "交易日期" in row_text or "发生额" in row_text or (
                "摘要" in row_text and "余额" in row_text
            ):
                new_map = self._build_col_map(cells)
                if new_map:
                    col_map = new_map
                continue  # skip header row itself

            if not any(cells):
                continue

            # Only parse if we have a usable column map
            if not col_map:
                continue

            draft = self._parse_data_row(cells, col_map)
            if draft:
                yield draft, col_map

    def _parse_data_row(
        self,
        cells: list[str],
        col_map: dict[str, int],
    ) -> RawTransactionDraft | None:
        """
        Extract one transaction using the header-driven column map.

        ICBC PDFs use a single signed amount column: '+' = income, '-' = expense.
        The balance column has NO sign.  Previous heuristic code matched unsigned
        numbers and therefore picked up balances instead of transaction amounts.
        """
        try:
            def get(field: str) -> str:
                idx = col_map.get(field)
                if idx is None or idx >= len(cells):
                    return ""
                return _clean_cell(cells[idx])

            # Date cell: strip ALL non-date chars including Chinese watermarks
            # that can interrupt the year digits (e.g. "行 20银26-04-24").
            date_raw = get("date")
            date_str = re.sub(r"[^\d\-/:]", "", date_raw) if date_raw else ""

            amount_raw = get("amount")   # may still contain watermark prefix
            summary    = get("summary") or None
            cpty_raw   = get("counterparty") or None

            # Fallback: locate date by scanning if col_map missing it
            if not date_str:
                for c in cells:
                    if re.match(r"\d{4}[-/]\d{2}[-/]\d{2}", c):
                        date_str = c
                        break

            # Extract the signed amount from within the cell.
            # ICBC cells look like "5 A -1.09" after watermark collapse;
            # a regex search finds the real value regardless of prefix noise.
            amount_str: str | None = None
            if amount_raw:
                m = re.search(r"([+\-]\d[\d,]*\.?\d*)", amount_raw)
                if m:
                    amount_str = m.group(1)
            # Fallback: scan all cells for a signed number
            if not amount_str:
                for c in cells:
                    clean = _clean_cell(c)
                    m = re.search(r"([+\-]\d[\d,]*\.?\d*)", clean)
                    if m:
                        amount_str = m.group(1)
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

            # Shadow detection
            text = f"{summary or ''} {cpty_raw or ''}"
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
                counterparty=cpty_raw,
                description=summary,
                payment_method_raw=payment_raw,
                txn_type_raw=summary,
                direction=direction,
                external_txn_id=None,
                external_merchant_id=None,
                is_group_payment=False,
                raw_json={"cells": cells, "col_map": col_map},
            )
        except Exception:
            return None
