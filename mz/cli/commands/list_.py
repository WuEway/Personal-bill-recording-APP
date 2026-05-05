from __future__ import annotations

import click
from rich.console import Console
from rich.table import Table
from rich import box

from mz.cli.context import get_connection
from mz.cli.ui import fmt_amount, inclusion_badge, make_table
from mz.services.inclusion import InclusionManager
from mz.services.coverage import CoverageDetector
from mz.utils.dates import current_month, month_range

console = Console()

SOURCE_LABELS = {
    "wechat": "WeChat",
    "alipay": "Alipay",
    "bank_pingan": "平安",
    "bank_icbc": "工行",
    "bank_ccb": "建行",
    "bank_boc": "中行",
    "bank_abc": "农行",
    "bank_cmb": "招行",
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


@cmd_list.command("files")
def list_files():
    """查看所有已导入账单文件（含编号/来源/时间段/条数）。"""
    from mz.repositories.imported_file_repo import ImportedFileRepository
    import os

    conn = get_connection()
    repo = ImportedFileRepository(conn)
    files = repo.list_all()
    conn.close()

    if not files:
        console.print("[dim]尚未导入任何账单文件[/dim]\n")
        return

    # Build short aliases: single file from source → source name; multiple → source_1, source_2
    from collections import Counter
    source_counts: Counter = Counter(f.source for f in files)
    source_seen: Counter = Counter()

    console.print("\n[bold]已导入账单文件[/bold]\n")
    t = make_table("ID", "别名", "来源", "账单周期", "条数", "文件")
    for f in files:
        count = source_counts[f.source]
        source_seen[f.source] += 1
        alias = f.source if count == 1 else f"{f.source}_{source_seen[f.source]}"
        src_label = SOURCE_LABELS.get(f.source, f.source)
        period = (
            f"{f.period_start.strftime('%Y-%m-%d')} ~ {f.period_end.strftime('%Y-%m-%d')}"
            if f.period_start and f.period_end else "—"
        )
        basename = os.path.basename(f.file_path)
        if len(basename) > 35:
            basename = basename[:32] + "..."
        t.add_row(str(f.id), alias, src_label, period, str(f.row_count), basename)

    console.print(t)
    console.print(
        f"共 {len(files)} 个文件  "
        "[dim]— 用 ID 或别名查看原始记录：mz list raw --file <ID 或别名>[/dim]\n"
    )


def _resolve_file_arg(conn, file_arg: str) -> tuple[int | None, str]:
    """
    Accept either a numeric ID ("3") or an alias ("bank_pingan", "wechat_2").
    Returns (resolved_file_id, display_label).
    """
    from collections import Counter
    from mz.repositories.imported_file_repo import ImportedFileRepository

    # Pure integer → treat as DB ID directly
    if file_arg.isdigit():
        fid = int(file_arg)
        row = conn.execute("SELECT source, file_path FROM imported_files WHERE id=?", (fid,)).fetchone()
        label = f"文件#{fid}" + (f" ({row[0]})" if row else "")
        return fid, label

    # String alias → rebuild alias→id mapping
    repo = ImportedFileRepository(conn)
    all_files = repo.list_all()
    counts: Counter = Counter(f.source for f in all_files)
    seen: Counter = Counter()
    for f in all_files:
        seen[f.source] += 1
        alias = f.source if counts[f.source] == 1 else f"{f.source}_{seen[f.source]}"
        if alias == file_arg:
            return f.id, f"{alias} (ID {f.id})"

    return None, f"未找到别名 '{file_arg}'"


@cmd_list.command("raw")
@click.option("--source", "-s", default=None,
              help="来源过滤: wechat / alipay / bank_pingan / bank_icbc / …")
@click.option("--file", "file_arg", default=None, type=str,
              help="按文件 ID 或别名过滤（见 mz list files）；优先于 --source")
@click.option("--month", "-m", default=None, help="月份 YYYY-MM（默认当月）")
@click.option("--transfers", is_flag=True, default=False,
              help="同时显示已标记为内部转账的记录")
def list_raw(source: str | None, file_arg: str | None, month: str | None, transfers: bool):
    """查看原始导入记录（用于核验原始账单数据）。

    \b
    示例：
      mz list raw --source wechat --month 2026-04
      mz list raw --file 3 --month 2026-04          # 按数字 ID
      mz list raw --file bank_pingan --month 2026-04 # 按别名
      mz list raw --month 2026-04                    # 所有来源
    """
    if month is None:
        month = current_month()
    start, end = month_range(month)

    conn = get_connection()
    from mz.repositories.raw_txn_repo import RawTransactionRepository
    raw_repo = RawTransactionRepository(conn)

    # --file (ID or alias) takes priority over --source
    if file_arg is not None:
        file_id, src_label = _resolve_file_arg(conn, file_arg)
        if file_id is None:
            console.print(f"[red]✗[/red] {src_label}\n")
            conn.close()
            return
        raws = [r for r in raw_repo.list_in_period(start, end) if r.source_file_id == file_id]
    else:
        raws = raw_repo.list_in_period(start, end, source=source)
        src_label = SOURCE_LABELS.get(source, source) if source else "全部"

    if not transfers:
        raws = [r for r in raws if not r.is_internal_transfer]

    console.print(f"\n[bold]{month} 原始账单 — {src_label}[/bold]\n")

    if not raws:
        console.print("[dim]无记录[/dim]\n")
        conn.close()
        return

    # Check which raw IDs have been linked as shadows (deduplicated)
    linked_ids: set[int] = set(
        row[0] for row in conn.execute("SELECT raw_txn_id FROM dedup_links").fetchall()
    )

    t = make_table("raw_id", "时间", "金额", "方向", "对方", "说明", "来源", "状态")
    for r in raws:
        direction_label = {"expense": "支出", "income": "收入", "transfer": "转账"}.get(
            r.direction, r.direction
        )
        src = SOURCE_LABELS.get(r.source, r.source)

        if r.is_internal_transfer:
            status = "[dim]内部转账[/dim]"
        elif r.id in linked_ids:
            status = "[cyan]已去重(影子)[/cyan]"
        else:
            status = "[green]主记录[/green]"

        t.add_row(
            str(r.id),
            r.txn_time.strftime("%m-%d %H:%M"),
            fmt_amount(r.amount_cents),
            direction_label,
            (r.counterparty or "")[:20],
            (r.description or "")[:25],
            src,
            status,
        )

    console.print(t)
    console.print(f"共 {len(raws)} 条原始记录\n")
    conn.close()


@cmd_list.command("shadows")
@click.option("--month", "-m", default=None, help="月份 YYYY-MM（默认当月）")
def list_shadows(month: str | None):
    """查看未成功匹配的银行影子记录（银行流水中含"财付通"/"支付宝"但未去重的条目）。"""
    if month is None:
        month = current_month()
    start, end = month_range(month)

    conn = get_connection()
    detector = CoverageDetector(conn)
    orphans = detector.list_all_orphan_shadows(start, end)
    conn.close()

    console.print(f"\n[bold]{month} 未匹配银行影子记录[/bold]\n")

    if not orphans:
        console.print("[green]✓ 无遗漏，所有银行影子记录已匹配[/green]\n")
        return

    console.print(
        '[dim]这些银行记录描述含"财付通"/"支付宝"，表明是微信/支付宝付款产生的扣款，'
        '但未找到对应的 App 账单记录与之配对。\n'
        '可能原因：App 账单时间段不覆盖该交易、金额有差异，或账单未导入。[/dim]\n'
    )

    t = make_table("raw_id", "日期", "金额", "银行来源", "描述")
    for o in orphans:
        t.add_row(
            str(o["id"]),
            o["date"],
            fmt_amount(o["amount_cents"]),
            SOURCE_LABELS.get(o["bank_source"], o["bank_source"]),
            o["desc"][:50],
        )

    console.print(t)
    console.print(f"共 {len(orphans)} 条未匹配记录\n")
