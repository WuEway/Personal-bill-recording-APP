from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from rich import box

from mz.cli.context import get_connection
from mz.cli.ui import warn
from mz.services.coverage import CoverageDetector
from mz.utils.dates import current_month, month_range

console = Console()


@click.command("coverage")
@click.option("--month", "-m", default=None, help="月份 YYYY-MM（默认当月）")
def cmd_coverage(month: str | None):
    """检测缺失账单，给出补传建议。"""
    if month is None:
        month = current_month()
    start, end = month_range(month)

    conn = get_connection()
    detector = CoverageDetector(conn)
    missing = detector.detect(start, end)
    conn.close()

    if not missing:
        console.print("[green]✓ 账单覆盖完整，无缺失账户。[/green]")
        return

    console.print(f"\n[bold yellow]⚠ 检测到 {len(missing)} 个可能缺失的账单[/bold yellow]\n")

    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold")
    t.add_column("优先级", width=8)
    t.add_column("账户")
    t.add_column("证据")

    for ma in missing:
        acc_label = f"{ma.institution}{'(' + ma.last_4 + ')' if ma.last_4 else ''}"
        priority_badge = "[red]高[/red]" if ma.priority == "high" else "[yellow]中[/yellow]"
        t.add_row(priority_badge, acc_label, "\n".join(ma.evidence[:3]))

    console.print(t)
    console.print(
        "\n[dim]运行 [cyan]mz import <文件>[/cyan] 导入对应账单后重新运行 dedupe[/dim]\n"
    )
