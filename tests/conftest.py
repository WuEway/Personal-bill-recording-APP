from __future__ import annotations

import csv
import io
from datetime import datetime
from pathlib import Path

import openpyxl
import pytest

from mz.db.connection import init_db, set_db_path, get_db


@pytest.fixture
def db_path(tmp_path: Path) -> Path:
    p = tmp_path / "test.db"
    set_db_path(p)
    init_db(p)
    return p


@pytest.fixture
def conn(db_path: Path):
    connection = get_db()
    yield connection
    connection.close()


# ── Synthetic file factories ──────────────────────────────────────────────

def make_wechat_xlsx(tmp_path: Path, rows: list[dict]) -> Path:
    """Create a minimal WeChat XLSX bill file."""
    path = tmp_path / "wechat_test.xlsx"
    wb = openpyxl.Workbook()
    ws = wb.active

    # Metadata rows
    ws.append(["微信支付账单明细（2026-04-01至2026-04-30）"])
    for _ in range(16):
        ws.append([""])
    ws.append(["交易时间", "交易类型", "交易对方", "商品", "收/支", "金额(元)", "支付方式", "当前状态", "交易单号", "商户单号", "备注"])

    for r in rows:
        ws.append([
            r.get("time", datetime(2026, 4, 15, 12, 0, 0)),
            r.get("type", "商户消费"),
            r.get("party", "测试商户"),
            r.get("item", "商品"),
            r.get("sign", "支出"),
            r.get("amount", 10.0),
            r.get("payment", "零钱"),
            r.get("status", "支付成功"),
            r.get("txn_id", "T001"),
            r.get("merchant_id", "M001"),
            r.get("note", ""),
        ])

    wb.save(path)
    return path


def make_alipay_csv(tmp_path: Path, rows: list[dict]) -> Path:
    """Create a minimal Alipay CSV bill file (GBK encoding)."""
    path = tmp_path / "alipay_test.csv"
    lines = []
    # Header lines
    for _ in range(22):
        lines.append("说明行,")
    lines.append("------------------------支付宝支付科技有限公司  电子客户回单------------------------,")
    lines.append("交易时间,交易分类,交易对方,对方账号,商品说明,收/支,金额,收/付款方式,交易状态,交易订单号,商家订单号,备注,")
    for r in rows:
        lines.append(",".join([
            r.get("time", "2026-04-15 12:00:00"),
            r.get("category", "其他"),
            r.get("party", "测试商户"),
            r.get("party_acc", ""),
            r.get("item", "商品"),
            r.get("sign", "支出"),
            str(r.get("amount", "10.00")),
            r.get("payment", "余额"),
            r.get("status", "交易成功"),
            r.get("txn_id", "A001"),
            r.get("merchant_id", "MA001"),
            r.get("note", ""),
            "",  # trailing comma
        ]))

    content = "\n".join(lines)
    path.write_bytes(content.encode("gbk"))
    return path
