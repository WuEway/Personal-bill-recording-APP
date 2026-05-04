from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from rich import box

from mz.cli.context import get_connection
from mz.cli.ui import fmt_amount, inclusion_badge, make_table
from mz.services.inclusion import InclusionManager
from mz.utils.dates import current_month, month_range

console = Console()

SOURCE_LABELS = {
    "wechat": "WeChat",
    "alipay": "Alipay",
    "bank_pingan": "平安",
    "bank_icbc": "工行",
    "bank_ccb": "建行",
}


@click.group("list")
def cmd_list():
    """查看交易列表。"""


@cmd_list.command("expense")
@click.option("--month", "-m", default=None, help="月份 YYYY-MM（默认当月）")
def list_expense(month: str | None):
    """查看支出分支（按时间倒序）。"""
    _show_branch("expense", month)


@cmd_list.command("income")
@click.option("--month", "-m", default=None, help="月份 YYYY-MM（默认当月）")
def list_income(month: str | None):
    """查看收入分支（按时间倒序）。"""
    _show_branch("income", month)


@cmd_list.command("group")
@click.option("--month", "-m", default=None, help="月份 YYYY-MM（默认当月）")
def list_group(month: str | None):
    """查看群收款独立分支。"""
    _show_group(month)


def _show_branch(branch: str, month: str | None) -> None:
    if month is None:
        month = current_month()
    start, end = month_range(month)

    conn = get_connection()
    from mz.repositories.account_repo import AccountRepository
    from mz.repositories.transaction_repo import TransactionRepository

    txn_repo = TransactionRepository(conn)
    acc_repo = AccountRepository(conn)

    txns = txn_repo.list_in_period(start, end, direction=branch)
    txns = [t for t in txns if not t.is_group_payment]

    label = "支出" if branch == "expense" else "收入"
    console.print(f"\n[bold]{month} {label}分支（按时间倒序）[/bold]\n")

    t = make_table("ID", "时间", "金额", "对方", "说明", "来源", "计入")
    total_in = 0

    for txn in txns:
        acc = acc_repo.get_by_id(txn.payment_account_id) if txn.payment_account_id else None
        raw_row = conn.execute(
            "SELECT source FROM raw_transactions WHERE id=?", (txn.primary_raw_id,)
        ).fetchone()
        source_str = SOURCE_LABELS.get(raw_row[0] if raw_row else "", raw_row[0] if raw_row else "")

        in_total = InclusionManager._effective(txn) in ("expense", "offset")
        badge = inclusion_badge(txn.inclusion, in_total, txn.is_group_payment)

        if in_total:
            total_in += abs(txn.amount_cents)

        t.add_row(
            str(txn.id),
            txn.txn_time.strftime("%m-%d %H:%M"),
            fmt_amount(txn.amount_cents),
            (txn.counterparty or "")[:20],
            (txn.description or "")[:25],
            source_str,
            badge,
        )

    console.print(t)
    console.print(
        f"合计（已计入）: [bold green]{fmt_amount(total_in)}[/bold green]，"
        f"共 {len(txns)} 条\n"
    )
    conn.close()


def _show_group(month: str | None) -> None:
    if month is None:
        month = current_month()
    start, end = month_range(month)

    conn = get_connection()
    from mz.repositories.transaction_repo import TransactionRepository

    txn_repo = TransactionRepository(conn)
    all_txns = txn_repo.list_in_period(start, end)
    group_txns = [t for t in all_txns if t.is_group_payment]

    console.print(f"\n[bold]{month} 群收款分支[/bold]\n")
    if not group_txns:
        console.print("[dim]本月无群收款记录[/dim]\n")
        conn.close()
        return

    t = make_table("ID", "时间", "金额", "对方", "说明", "方向", "计入")
    for txn in group_txns:
        in_total = InclusionManager._effective(txn) in ("expense", "offset")
        badge = inclusion_badge(txn.inclusion, in_total, True)
        t.add_row(
            str(txn.id),
            txn.txn_time.strftime("%m-%d %H:%M"),
            fmt_amount(txn.amount_cents),
            (txn.counterparty or "")[:20],
            (txn.description or "")[:25],
            txn.direction,
            badge,
        )
    console.print(t)
    console.print(f"共 {len(group_txns)} 条，默认全部不计入总支出\n")
    conn.close()
