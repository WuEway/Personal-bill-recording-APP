from __future__ import annotations

import click

from mz.cli.commands.init import cmd_init
from mz.cli.commands.formats import cmd_formats
from mz.cli.commands.import_ import cmd_import
from mz.cli.commands.dedupe import cmd_dedupe
from mz.cli.commands.list_ import cmd_list
from mz.cli.commands.inclusion import (
    cmd_include,
    cmd_exclude,
    cmd_offset,
    cmd_reset_inclusion,
)
from mz.cli.commands.category import cmd_category
from mz.cli.commands.entry import cmd_entry
from mz.cli.commands.report import cmd_report
from mz.cli.commands.coverage import cmd_coverage
from mz.cli.commands.explain import cmd_explain
from mz.cli.commands.db import cmd_db
from mz.cli.commands.delete_file import cmd_delete_file


@click.group()
@click.version_option("2.0.0", prog_name="mz")
def cli():
    """MZ — 个人月度对账系统

    聚合微信/支付宝/银行账单，自动去重，计算当月真实支出。
    """


cli.add_command(cmd_init)
cli.add_command(cmd_formats)
cli.add_command(cmd_import)
cli.add_command(cmd_dedupe)
cli.add_command(cmd_list)
cli.add_command(cmd_include)
cli.add_command(cmd_exclude)
cli.add_command(cmd_offset)
cli.add_command(cmd_reset_inclusion)
cli.add_command(cmd_category)
cli.add_command(cmd_entry)
cli.add_command(cmd_report)
cli.add_command(cmd_coverage)
cli.add_command(cmd_explain)
cli.add_command(cmd_db)
cli.add_command(cmd_delete_file)
