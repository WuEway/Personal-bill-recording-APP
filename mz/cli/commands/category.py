from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from rich import box

from mz.cli.context import get_connection
from mz.cli.ui import error, success, fmt_amount
from mz.services.category_service import ManualCategoryService

console = Console()


@click.group("category")
def cmd_category():
    """管理重点关注类目（F2）。"""


@cmd_category.command("list")
def category_list():
    """列出所有类目及预算进度。"""
    conn = get_connection()
    svc = ManualCategoryService(conn)
    progresses = svc.get_all_progress()

    if not progresses:
        console.print("[dim]暂无类目。使用 mz category add <名称> 添加。[/dim]")
        conn.close()
        return

    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    t.add_column("ID")
    t.add_column("类目")
    t.add_column("本月已用")
    t.add_column("月限额")
    t.add_column("年度已用")
    t.add_column("年限额")
    t.add_column("提醒")

    for p in progresses:
        t.add_row(
            str(p.category_id),
            f"{p.icon} {p.name}",
            fmt_amount(p.month_spent_cents),
            fmt_amount(p.monthly_budget_cents) if p.monthly_budget_cents else "—",
            fmt_amount(p.year_spent_cents),
            fmt_amount(p.yearly_budget_cents) if p.yearly_budget_cents else "—",
            p.alert_text[:50],
        )

    console.print(t)
    conn.close()


@cmd_category.command("add")
@click.argument("name")
@click.option("--icon", "-i", default=None, help="图标（emoji）")
@click.option("--monthly", "-M", type=float, default=None, help="月预算（元）")
@click.option("--yearly", "-Y", type=float, default=None, help="年预算（元）")
def category_add(name: str, icon: str | None, monthly: float | None, yearly: float | None):
    """添加重点关注类目。"""
    conn = get_connection()
    svc = ManualCategoryService(conn)
    try:
        cat_id = svc.add_category(name, icon=icon, monthly_budget=monthly, yearly_budget=yearly)
        success(f"类目 '{name}' 已创建（ID: {cat_id}）")
        if monthly:
            success(f"  月预算: {fmt_amount(int(monthly * 100))}")
        if yearly:
            success(f"  年预算: {fmt_amount(int(yearly * 100))}")
    except ValueError as e:
        error(str(e))
    conn.close()


@cmd_category.command("remove")
@click.argument("name")
def category_remove(name: str):
    """删除（停用）类目。"""
    conn = get_connection()
    svc = ManualCategoryService(conn)
    try:
        svc.remove_category(name)
        success(f"类目 '{name}' 已删除")
    except ValueError as e:
        error(str(e))
    conn.close()


@cmd_category.command("set-budget")
@click.argument("name")
@click.option("--monthly", "-M", type=float, default=None, help="月预算（元）")
@click.option("--yearly", "-Y", type=float, default=None, help="年预算（元）")
def category_set_budget(name: str, monthly: float | None, yearly: float | None):
    """设置类目限额。"""
    conn = get_connection()
    svc = ManualCategoryService(conn)
    try:
        svc.set_budget(name, monthly=monthly, yearly=yearly)
        success(f"类目 '{name}' 预算已更新")
    except ValueError as e:
        error(str(e))
    conn.close()
