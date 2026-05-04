from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from rich import box

from mz.cli.context import get_connection
from mz.cli.ui import fmt_amount
from mz.repositories.account_repo import AccountRepository
from mz.repositories.raw_txn_repo import RawTransactionRepository
from mz.repositories.transaction_repo import TransactionRepository
from mz.services.inclusion import InclusionManager

console = Console()


@click.command("explain")
@click.argument("txn_id", type=int)
def cmd_explain(txn_id: int):
    """展示单条交易的详细信息及去重决策。"""
    conn = get_connection()
    txn_repo = TransactionRepository(conn)
    raw_repo = RawTransactionRepository(conn)
    acc_repo = AccountRepository(conn)

    txn = txn_repo.get_by_id(txn_id)
    if not txn:
        console.print(f"[red]✗ 交易 {txn_id} 不存在[/red]")
        conn.close()
        return

    acc = acc_repo.get_by_id(txn.payment_account_id) if txn.payment_account_id else None
    effective = InclusionManager._effective(txn)
    in_label = {
        "expense": "计入支出",
        "offset": "抵充支出",
        "excluded": "不计入",
    }.get(effective, "—")

    console.print(f"\n[bold]Canonical Transaction #{txn_id}[/bold]")
    info_rows = [
        ("时间", txn.txn_time.strftime("%Y-%m-%d %H:%M:%S")),
        ("金额", fmt_amount(txn.amount_cents)),
        ("对方", txn.counterparty or "—"),
        ("说明", txn.description or "—"),
        ("支付账户", acc.name if acc else "—"),
        ("方向", txn.direction),
        ("inclusion", f"{txn.inclusion} → {in_label}"),
        ("是否群收款", "是" if txn.is_group_payment else "否"),
    ]
    if txn.manual_category_id:
        info_rows.append(("重点类目 ID", str(txn.manual_category_id)))

    for k, v in info_rows:
        console.print(f"  {k:<12} {v}")

    # Raw source records
    primary = raw_repo.get_by_id(txn.primary_raw_id)
    if primary:
        console.print(f"\n[bold]源记录合并：[/bold]")
        console.print(
            f"  [green]• [self][/green]  raw#{primary.id} ({primary.source})  主记录"
        )

    links = txn_repo.list_dedup_links(txn_id)
    for link in links:
        console.print(
            f"  [yellow]• [match][/yellow] raw#{link['raw_txn_id']} ({link['source']})  "
            f"影子, conf={link['match_confidence']:.2f}"
        )
        console.print(f"           匹配理由: {link['match_reason']}")

    if not links:
        console.print("  (无跨平台关联)")

    console.print()
    conn.close()
