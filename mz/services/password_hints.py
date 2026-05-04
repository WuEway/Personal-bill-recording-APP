from __future__ import annotations

from pathlib import Path

PASSWORD_HINTS: dict[str, str] = {
    "bank_icbc": "工商银行：身份证后 6 位（默认）",
    "bank_ccb": "建设银行：身份证后 6 位（默认）",
    "bank_pingan": "平安银行：通常无密码",
    "bank_boc": "中国银行：身份证后 6 位（默认）",
    "wechat_zip": "微信账单 ZIP：导出时邮件中给出的 6 位数字",
    "alipay_zip": "支付宝账单 ZIP：导出时设置的密码（一般无）",
    "unknown": "请联系账单来源机构确认密码规则",
}


def detect_source_for_password_hint(file_path: Path) -> str:
    name = file_path.name
    name_upper = name.upper()
    if "工商" in name or "ICBC" in name_upper:
        return "bank_icbc"
    if "建设" in name or "CCB" in name_upper:
        return "bank_ccb"
    if "平安" in name or "PINGAN" in name_upper:
        return "bank_pingan"
    if "中国银行" in name or "BOC" in name_upper:
        return "bank_boc"
    if "微信" in name and name.endswith(".zip"):
        return "wechat_zip"
    if "支付宝" in name and name.endswith(".zip"):
        return "alipay_zip"
    return "unknown"


def get_hint(file_path: Path) -> str:
    source = detect_source_for_password_hint(file_path)
    return PASSWORD_HINTS.get(source, PASSWORD_HINTS["unknown"])
