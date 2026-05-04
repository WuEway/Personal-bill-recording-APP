from __future__ import annotations

from rich.console import Console
from rich.table import Table
from rich import box

console = Console()


def success(msg: str) -> None:
    console.print(f"[green]✓[/green] {msg}")


def info(msg: str) -> None:
    console.print(f"[cyan]ℹ[/cyan] {msg}")


def warn(msg: str) -> None:
    console.print(f"[yellow]⚠[/yellow] {msg}")


def error(msg: str) -> None:
    console.print(f"[red]✗[/red] {msg}")


def make_table(*headers: str, box_style=box.SIMPLE_HEAVY) -> Table:
    t = Table(box=box_style, show_header=True, header_style="bold cyan")
    for h in headers:
        t.add_column(h)
    return t


def fmt_amount(cents: int) -> str:
    return f"¥{abs(cents)/100:,.2f}"


def inclusion_badge(inclusion: str, in_total: bool, is_group: bool) -> str:
    if is_group:
        return "[dim]☐ (group)[/dim]"
    if in_total:
        return "[green]✓[/green]"
    if inclusion == "excluded":
        return "[red]✗[/red]"
    return "[dim]☐[/dim]"
