from __future__ import annotations

import click
from rich.console import Console

from mz.cli.context import get_connection
from mz.cli.ui import error, success
from mz.services.inclusion import InclusionManager

console = Console()


def _parse_ids(ids: tuple[str, ...]) -> list[int]:
    result = []
    for s in ids:
        for part in s.split(","):
            part = part.strip()
            if part:
                try:
                    result.append(int(part))
                except ValueError:
                    raise click.BadParameter(f"无效 ID: {part!r}")
    return result


@click.command("include")
@click.argument("txn_ids", nargs=-1, required=True)
@click.option("--note", default="", help="原因备注")
def cmd_include(txn_ids: tuple[str, ...], note: str):
    """显式将交易标记为计入支出。"""
    conn = get_connection()
    mgr = InclusionManager(conn)
    ids = _parse_ids(txn_ids)
    for tid in ids:
        try:
            mgr.set(tid, "included", note)
            success(f"交易 {tid} 已标记为计入")
        except ValueError as e:
            error(str(e))
    conn.close()


@click.command("exclude")
@click.argument("txn_ids", nargs=-1, required=True)
@click.option("--note", default="", help="原因备注")
def cmd_exclude(txn_ids: tuple[str, ...], note: str):
    """显式将交易标记为不计入支出。"""
    conn = get_connection()
    mgr = InclusionManager(conn)
    ids = _parse_ids(txn_ids)
    for tid in ids:
        try:
            mgr.set(tid, "excluded", note)
            success(f"交易 {tid} 已标记为排除")
        except ValueError as e:
            error(str(e))
    conn.close()


@click.command("offset")
@click.argument("txn_ids", nargs=-1, required=True)
@click.option("--note", default="", help="原因备注")
def cmd_offset(txn_ids: tuple[str, ...], note: str):
    """将收入交易用于抵充本月支出。"""
    conn = get_connection()
    mgr = InclusionManager(conn)
    ids = _parse_ids(txn_ids)
    for tid in ids:
        try:
            mgr.set(tid, "offset", note)
            success(f"收入 {tid} 已标记为抵充支出")
        except ValueError as e:
            error(str(e))
    conn.close()


@click.command("reset-inclusion")
@click.argument("txn_ids", nargs=-1, required=True)
def cmd_reset_inclusion(txn_ids: tuple[str, ...]):
    """重置交易的 inclusion 标记为默认（auto）。"""
    conn = get_connection()
    mgr = InclusionManager(conn)
    ids = _parse_ids(txn_ids)
    for tid in ids:
        try:
            mgr.reset(tid)
            success(f"交易 {tid} 已重置为默认")
        except ValueError as e:
            error(str(e))
    conn.close()
