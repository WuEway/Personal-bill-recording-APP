from __future__ import annotations

import click
from rich.console import Console

from mz.cli.context import get_connection
from mz.cli.ui import info, success
from mz.services.dedupe.engine import DedupeEngine
from mz.utils.dates import current_month, month_range

console = Console()


@click.command("dedupe")
@click.option("--month", "-m", default=None, help="指定月份 YYYY-MM（默认当月）")
def cmd_dedupe(month: str | None):
    """对账单执行跨平台去重，生成规范交易记录。"""
    if month is None:
        month = current_month()
    start, end = month_range(month)

    conn = get_connection()
    engine = DedupeEngine(conn)

    info(f"正在处理 {month} 的交易数据...")
    stats = engine.run(period_start=start, period_end=end)

    success(f"去重完成：")
    info(f"  新建规范交易: {stats['created']} 笔")
    info(f"  银行影子已关联: {stats['bank_linked_as_shadow']} 笔")
    info(f"  银行独立记录: {stats['bank_standalone']} 笔")

    console.print("\n[dim]运行 [cyan]mz report[/cyan] 查看月度报告[/dim]")
    conn.close()
