from __future__ import annotations

from datetime import datetime

import click
from rich.console import Console
from rich.table import Table
from rich import box

from mz.cli.context import get_connection
from mz.cli.ui import error, fmt_amount, success
from mz.services.category_service import ManualCategoryService
from mz.repositories.category_repo import CategoryRepository
from mz.utils.dates import current_month, month_range

console = Console()


@click.group("entry")
def cmd_entry():
    """管理重点类目的手动录入条目。"""


@cmd_entry.command("add")
@click.argument("category")
@click.argument("amount", type=float)
@click.argument("description")
@click.option("--date", "-d", "date_str", default=None, help="日期 YYYY-MM-DD（默认今日）")
@click.option("--link", "-l", "txn_id", type=int, default=None, help="关联交易 ID")
def entry_add(
    category: str, amount: float, description: str, date_str: str | None, txn_id: int | None
):
    """录入类目消费条目。"""
    if date_str:
        txn_time = datetime.strptime(date_str, "%Y-%m-%d")
    else:
        txn_time = datetime.now()

    conn = get_connection()
    svc = ManualCategoryService(conn)
    try:
        eid = svc.add_entry(
            category_name=category,
            amount=amount,
            description=description,
            txn_time=txn_time,
            linked_txn_id=txn_id,
        )
        success(f"已录入：{category} {fmt_amount(int(amount * 100))} — {description} (ID: {eid})")
    except ValueError as e:
        error(str(e))
    conn.close()


@cmd_entry.command("list")
@click.option("--month", "-m", default=None, help="月份 YYYY-MM（默认当月）")
@click.option("--category", "-c", "cat_name", default=None, help="筛选类目")
def entry_list(month: str | None, cat_name: str | None):
    """列出手动录入条目。"""
    if month is None:
        month = current_month()
    start, end = month_range(month)

    conn = get_connection()
    cat_repo = CategoryRepository(conn)

    cat_id = None
    if cat_name:
        cat = cat_repo.get_category_by_name(cat_name)
        if not cat:
            error(f"类目 '{cat_name}' 不存在")
            conn.close()
            return
        cat_id = cat.id

    entries = cat_repo.list_entries(category_id=cat_id, period_start=start, period_end=end)

    t = Table(box=box.SIMPLE_HEAVY, show_header=True, header_style="bold cyan")
    t.add_column("ID")
    t.add_column("日期")
    t.add_column("类目")
    t.add_column("金额")
    t.add_column("说明")
    t.add_column("关联交易")

    for e in entries:
        cat = cat_repo.get_category_by_id(e.category_id)
        cat_display = f"{cat.icon or ''} {cat.name}" if cat else str(e.category_id)
        t.add_row(
            str(e.id),
            e.txn_time.strftime("%Y-%m-%d"),
            cat_display,
            fmt_amount(e.amount_cents),
            e.description or "",
            str(e.linked_txn_id) if e.linked_txn_id else "—",
        )

    console.print(t)
    conn.close()


@cmd_entry.command("remove")
@click.argument("entry_id", type=int)
def entry_remove(entry_id: int):
    """删除录入条目。"""
    conn = get_connection()
    cat_repo = CategoryRepository(conn)
    if cat_repo.delete_entry(entry_id):
        success(f"条目 {entry_id} 已删除")
    else:
        error(f"条目 {entry_id} 不存在")
    conn.close()
