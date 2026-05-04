from __future__ import annotations

from pathlib import Path


def read_text_auto(file_path: Path) -> str:
    """Try UTF-8 first, fallback to GBK / GB18030."""
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            return file_path.read_text(encoding=enc)
        except (UnicodeDecodeError, LookupError):
            continue
    return file_path.read_text(encoding="latin-1")


def open_csv_auto(file_path: Path):
    """Return (file_handle, encoding) detecting encoding automatically."""
    for enc in ("utf-8-sig", "utf-8", "gbk", "gb18030"):
        try:
            content = file_path.read_bytes().decode(enc)
            return content, enc
        except (UnicodeDecodeError, LookupError):
            continue
    content = file_path.read_bytes().decode("latin-1")
    return content, "latin-1"
