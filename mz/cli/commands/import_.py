from __future__ import annotations

from pathlib import Path

import click
from rich.console import Console

from mz.cli.context import get_connection
from mz.cli.ui import error, info, success, warn
from mz.services.file_unpack import PasswordRequired
from mz.services.import_service import ImportService

console = Console()


@click.command("import")
@click.argument("file", type=click.Path(exists=True, path_type=Path))
@click.option("--source", "-s", default=None, help="手动指定来源 (wechat/alipay/bank_pingan/bank_icbc)")
@click.option("--password", "-p", default=None, help="加密文件密码")
def cmd_import(file: Path, source: str | None, password: str | None):
    """导入账单文件（支持 .xlsx / .csv / .pdf / .zip）。"""
    conn = get_connection()
    user_name = conn.execute(
        "SELECT value FROM app_config WHERE key='user_name'"
    ).fetchone()
    user_name_val = user_name[0] if user_name else None

    svc = ImportService(conn, user_name=user_name_val)

    def pwd_callback(fp: Path, hint: str) -> str:
        console.print(f"\n[yellow]检测到加密文件：{fp.name}[/yellow]")
        console.print(f"[dim]{hint}[/dim]")
        return click.prompt("请输入密码", hide_input=True)

    try:
        results = svc.import_file(
            file,
            password=password,
            source_hint=source,
            password_callback=pwd_callback,
        )
    except PasswordRequired as e:
        error(f"文件加密，需要密码：{e.hint}")
        error("请使用 --password 参数提供密码")
        return
    except ValueError as e:
        error(str(e))
        return

    for res in results:
        if res.skipped_duplicate:
            warn(f"该文件已导入过，跳过。")
            continue

        success(f"来源: {res.source}")
        info(f"解析行数: {res.rows_parsed}")
        info(f"新增入库: {res.rows_inserted}")
        if res.rows_duplicate:
            info(f"跳过重复: {res.rows_duplicate}")
        if res.internal_transfers_detected:
            info(f"检测到内部转账: {res.internal_transfers_detected} 笔")
        if res.period_start and res.period_end:
            info(f"账单周期: {res.period_start} 至 {res.period_end}")

    console.print(
        "\n[dim]提示：运行 [cyan]mz dedupe[/cyan] 进行跨平台去重后再查看报告[/dim]"
    )
    conn.close()
