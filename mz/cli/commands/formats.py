from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from rich import box

console = Console()

FORMAT_INFO = [
    (
        "微信支付账单",
        ".xlsx, .csv, .zip",
        '微信 → 我 → 服务 → 钱包 → 账单 → 常见问题 → 下载账单\n'
        '  ZIP 包内含 CSV，下载邮件中给出 6 位密码',
    ),
    (
        "支付宝交易明细",
        ".csv, .zip",
        '支付宝 → 账单 → 右上角设置 → 开具交易流水证明\n'
        '  文件为 GBK 编码；前 22 行为说明',
    ),
    (
        "平安银行账单",
        ".pdf",
        '平安银行 App → 我的账户 → 交易明细 → 申请回单\n'
        '  PDF 含水印，通常无密码',
    ),
    (
        "工商银行账单",
        ".pdf",
        '工商银行 App → 我的账户 → 历史明细 → 申请明细 PDF\n'
        '  PDF 通常加密，密码为身份证后 6 位',
    ),
    (
        "建设银行账单",
        ".pdf",
        '建设银行 App → 账户详情 → 申请交易明细\n'
        '  PDF 通常加密，密码为身份证后 6 位',
    ),
]


@click.command("formats")
def cmd_formats():
    """列出支持的账单文件格式及导出指引。"""
    console.print("\n[bold cyan]MZ 支持的账单格式[/bold cyan]\n")

    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    t.add_column("账单来源", style="bold")
    t.add_column("格式")
    t.add_column("导出说明")

    for name, fmt, guide in FORMAT_INFO:
        t.add_row(name, fmt, guide)

    console.print(t)
    console.print(
        "[dim]提示：所有 PDF 银行账单可能加密；"
        "导入时通过 --password 参数提供密码，或在交互提示时输入。[/dim]\n"
    )
