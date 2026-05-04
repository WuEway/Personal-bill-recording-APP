from __future__ import annotations

import json
import shutil
from datetime import datetime
from pathlib import Path

import click
from rich.console import Console
from rich.prompt import Confirm

from mz.cli.context import get_connection
from mz.cli.ui import error, info, success, warn
from mz.db.connection import get_db_path, init_db

console = Console()


@click.group("db")
def cmd_db():
    """数据库管理命令。"""


@cmd_db.command("reset")
@click.option("--force", is_flag=True, help="跳过确认直接重置")
def db_reset(force: bool):
    """清空数据库（危险操作）。"""
    if not force:
        if not Confirm.ask("[bold red]警告：此操作将删除所有数据！确认重置？[/bold red]", default=False):
            info("已取消")
            return
    db_path = get_db_path()
    if db_path.exists():
        db_path.unlink()
    init_db()
    success("数据库已重置")


@cmd_db.command("export")
@click.argument("output", type=click.Path(path_type=Path), default=None, required=False)
def db_export(output: Path | None):
    """备份数据库到指定文件。"""
    src = get_db_path()
    if not src.exists():
        error("数据库不存在")
        return
    if output is None:
        ts = datetime.now().strftime("%Y%m%d_%H%M%S")
        output = Path(f"mz_backup_{ts}.db")
    shutil.copy2(src, output)
    success(f"数据库已备份到: {output}")


@cmd_db.command("info")
def db_info():
    """显示数据库统计信息。"""
    conn = get_connection()
    tables = ["accounts", "imported_files", "raw_transactions", "transactions", "manual_categories", "manual_entries"]
    console.print("\n[bold]数据库统计[/bold]\n")
    for table in tables:
        count = conn.execute(f"SELECT COUNT(*) FROM {table}").fetchone()[0]
        console.print(f"  {table:<25} {count:>6} 条")
    db_path = get_db_path()
    size_kb = db_path.stat().st_size / 1024 if db_path.exists() else 0
    console.print(f"\n  数据库路径: {db_path}")
    console.print(f"  文件大小:   {size_kb:.1f} KB\n")
    conn.close()
