from __future__ import annotations

from pathlib import Path

from mz.importer.base import BaseImporter
from mz.importer.wechat import WechatImporter
from mz.importer.alipay import AlipayCsvImporter
from mz.importer.bank.pingan import PinganPdfImporter
from mz.importer.bank.icbc import IcbcPdfImporter

IMPORTERS: list[BaseImporter] = [
    WechatImporter(),
    AlipayCsvImporter(),
    PinganPdfImporter(),
    IcbcPdfImporter(),
]


def list_supported_formats() -> dict[str, list[str]]:
    return {imp.DISPLAY_NAME: imp.SUPPORTED_FORMATS for imp in IMPORTERS}


def find_importer(
    file_path: Path, file_format: str, hint: str | None = None
) -> BaseImporter:
    if hint:
        for imp in IMPORTERS:
            if imp.SOURCE_NAME == hint:
                return imp
        raise ValueError(f"未知账单来源: {hint}")
    for imp in IMPORTERS:
        if file_format in imp.SUPPORTED_FORMATS and imp.detect(file_path, file_format):
            return imp
    raise ValueError(
        f"无法识别文件格式: {file_path.name}（文件格式: .{file_format}）\n"
        "请用 --source 参数手动指定来源，或运行 mz formats 查看支持的格式。"
    )
