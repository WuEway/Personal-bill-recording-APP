from __future__ import annotations

import json
from datetime import date

import click
from rich.console import Console
from rich.panel import Panel
from rich.table import Table
from rich import box

from mz.cli.context import get_connection
from mz.cli.ui import fmt_amount
from mz.services.reporter import Reporter
from mz.utils.dates import current_month, month_range

console = Console()


@click.command("report")
@click.option("--month", "-m", default=None, help="月份 YYYY-MM（默认当月）")
@click.option("--format", "-f", "fmt", default="table", type=click.Choice(["table", "json", "md"]))
def cmd_report(month: str | None, fmt: str):
    """生成月度对账报告（支出/收入/类目进度）。"""
    if month is None:
        month = current_month()
    start, end = month_range(month)

    conn = get_connection()
    reporter = Reporter(conn)
    report = reporter.build_report(start, end)
    conn.close()

    if fmt == "json":
        _print_json(report)
    elif fmt == "md":
        _print_md(report, month)
    else:
        _print_table(report, month)


def _print_table(report, month: str) -> None:
    lines = [
        f"   [bold cyan]月度账单 — {month}[/bold cyan]",
        "",
        f"   📊 [bold]当月总支出  {fmt_amount(report.total_expense_cents)}[/bold]",
        f"       ├─ 原始支出  {fmt_amount(report.raw_expense_cents)}",
        f"       ├─ 收入抵充  {fmt_amount(report.offset_income_cents)}  ({_count_offset(report)} 项)",
        "",
        f"   📥 当月收入  {fmt_amount(report.total_income_cents)}  [dim](默认不抵充)[/dim]",
    ]

    if report.category_progresses:
        lines.append("")
        lines.append("   📌 [bold]重点类目[/bold]")
        for p in report.category_progresses:
            lines.append(f"      {p.icon or '•'} {p.name:<12} {p.alert_text}")

    if report.missing_accounts:
        lines.append("")
        lines.append("   ⚠️  [bold yellow]待补账单[/bold yellow]")
        for ma in report.missing_accounts:
            acc_label = (
                f"{ma.institution}{'(' + ma.last_4 + ')' if ma.last_4 else ''}"
            )
            ev = "; ".join(ma.evidence[:2])
            lines.append(f"      • {acc_label} — {ev}")

    content = "\n".join(lines)
    console.print(Panel(content, expand=False, border_style="cyan"))


def _count_offset(report) -> int:
    return sum(1 for r in report.income_branch if r.inclusion == "offset")


def _print_json(report) -> None:
    data = {
        "period": [report.period[0].isoformat(), report.period[1].isoformat()],
        "total_expense_cents": report.total_expense_cents,
        "raw_expense_cents": report.raw_expense_cents,
        "offset_income_cents": report.offset_income_cents,
        "total_income_cents": report.total_income_cents,
        "expense_count": len(report.expense_branch),
        "income_count": len(report.income_branch),
        "group_payment_count": len(report.group_payment_branch),
        "categories": [
            {
                "name": p.name,
                "month_spent_cents": p.month_spent_cents,
                "monthly_budget_cents": p.monthly_budget_cents,
                "year_spent_cents": p.year_spent_cents,
                "yearly_budget_cents": p.yearly_budget_cents,
            }
            for p in report.category_progresses
        ],
    }
    console.print(json.dumps(data, ensure_ascii=False, indent=2))


def _print_md(report, month: str) -> None:
    lines = [
        f"# 月度账单 — {month}",
        "",
        "## 总览",
        "",
        f"| 项目 | 金额 |",
        f"|---|---|",
        f"| 当月总支出 | {fmt_amount(report.total_expense_cents)} |",
        f"| 原始支出 | {fmt_amount(report.raw_expense_cents)} |",
        f"| 收入抵充 | {fmt_amount(report.offset_income_cents)} |",
        f"| 当月收入 | {fmt_amount(report.total_income_cents)} |",
        "",
    ]
    if report.category_progresses:
        lines += [
            "## 重点类目",
            "",
            "| 类目 | 本月 | 月限额 | 年度 | 年限额 |",
            "|---|---|---|---|---|",
        ]
        for p in report.category_progresses:
            lines.append(
                f"| {p.icon or ''} {p.name} "
                f"| {fmt_amount(p.month_spent_cents)} "
                f"| {fmt_amount(p.monthly_budget_cents) if p.monthly_budget_cents else '—'} "
                f"| {fmt_amount(p.year_spent_cents)} "
                f"| {fmt_amount(p.yearly_budget_cents) if p.yearly_budget_cents else '—'} |"
            )
        lines.append("")

    console.print("\n".join(lines))
