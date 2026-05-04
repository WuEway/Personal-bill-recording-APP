from __future__ import annotations

import click
from rich.console import Console
from rich.prompt import Confirm, Prompt

from mz.cli.context import get_connection
from mz.cli.ui import success, info
from mz.services.category_service import DEFAULT_CATEGORY_POOL

console = Console()


@click.command("init")
@click.pass_context
def cmd_init(ctx):
    """引导式初始化：设置用户名、选择重点类目。"""
    conn = get_connection()

    # Check if already onboarded
    row = conn.execute("SELECT value FROM app_config WHERE key='onboarded'").fetchone()
    if row and row[0] == "1":
        if not Confirm.ask("已完成初始化。是否重新配置？", default=False):
            return

    console.print("\n[bold cyan]欢迎使用 MZ 个人月度对账系统[/bold cyan]\n")

    user_name = Prompt.ask("请输入您的姓名（用于识别转账给自己）", default="")
    if user_name:
        conn.execute(
            "INSERT OR REPLACE INTO app_config(key, value) VALUES('user_name', ?)",
            (user_name,),
        )
        conn.commit()

    # Category selection
    console.print("\n[bold]请选择您的重点关注类目[/bold]（输入序号，多个用空格隔开，直接回车跳过）：\n")
    for i, (name, icon) in enumerate(DEFAULT_CATEGORY_POOL, 1):
        console.print(f"  {i:2d}. {icon} {name}")

    selection = Prompt.ask("\n选择序号", default="")
    if selection.strip():
        from mz.services.category_service import ManualCategoryService

        svc = ManualCategoryService(conn)
        for idx_str in selection.split():
            try:
                idx = int(idx_str) - 1
                if 0 <= idx < len(DEFAULT_CATEGORY_POOL):
                    name, icon = DEFAULT_CATEGORY_POOL[idx]
                    try:
                        svc.add_category(name, icon=icon)
                        success(f"已添加类目：{icon} {name}")
                    except ValueError:
                        pass  # already exists
            except ValueError:
                pass

    conn.execute(
        "INSERT OR REPLACE INTO app_config(key, value) VALUES('onboarded', '1')"
    )
    conn.commit()
    conn.close()

    console.print(
        "\n[bold green]初始化完成！[/bold green]\n"
        "接下来：\n"
        "  • 运行 [cyan]mz formats[/cyan] 查看支持的账单格式\n"
        "  • 运行 [cyan]mz import <文件>[/cyan] 导入账单\n"
        "  • 运行 [cyan]mz report[/cyan] 查看月度报告\n"
    )
