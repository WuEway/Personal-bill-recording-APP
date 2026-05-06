from __future__ import annotations

import click
from rich.console import Console
from rich.prompt import Confirm

from mz.cli.context import get_connection
from mz.cli.ui import error, info, success, warn
from mz.cli.commands.list_ import SOURCE_LABELS, _build_alias
from collections import Counter

console = Console()


@click.command("delete-file")
@click.argument("file_ref")
@click.option("--force", is_flag=True, help="跳过确认")
def cmd_delete_file(file_ref: str, force: bool):
    """删除一个已导入的账单文件及其全部原始记录和规范交易。

    \b
    FILE_REF 可以是数字 ID 或别名（见 mz list files）：
      mz delete-file 3
      mz delete-file pingan_8223
      mz delete-file icbc_6930

    删除后建议运行 mz dedupe --month <月份> 重新计算。
    """
    conn = get_connection()

    # ── Resolve file ref ──────────────────────────────────────────────────────
    file_id: int | None = None
    file_source: str = ""

    if file_ref.isdigit():
        row = conn.execute(
            "SELECT id, source, file_path FROM imported_files WHERE id=?",
            (int(file_ref),)
        ).fetchone()
        if row:
            file_id = row["id"]
            file_source = row["source"]
    else:
        # Resolve alias
        from mz.repositories.imported_file_repo import ImportedFileRepository
        repo = ImportedFileRepository(conn)
        all_files = repo.list_all()
        counts: Counter = Counter(f.source for f in all_files)
        seen: Counter = Counter()
        for f in all_files:
            seen[f.source] += 1
            alias = _build_alias(f, counts, seen)
            if alias == file_ref:
                file_id = f.id
                file_source = f.source
                break

    if file_id is None:
        error(f"找不到文件：{file_ref}（运行 mz list files 查看可用 ID 和别名）")
        conn.close()
        return

    # ── Show what will be deleted ─────────────────────────────────────────────
    raw_count = conn.execute(
        "SELECT COUNT(*) FROM raw_transactions WHERE source_file_id=?", (file_id,)
    ).fetchone()[0]
    src_label = SOURCE_LABELS.get(file_source, file_source)

    info(f"文件 ID={file_id}  来源={src_label}")
    info(f"将删除 {raw_count} 条原始记录及其衍生的规范交易")
    warn("此操作不可撤销。删除后请重新运行 mz dedupe 更新账单统计。")

    if not force:
        if not Confirm.ask("[bold red]确认删除？[/bold red]", default=False):
            info("已取消")
            conn.close()
            return

    # ── Cascade delete ────────────────────────────────────────────────────────
    # Order matters: dedup_links → transactions → raw_transactions → imported_file

    # 1. Find raw IDs for this file
    raw_ids = [
        r[0] for r in conn.execute(
            "SELECT id FROM raw_transactions WHERE source_file_id=?", (file_id,)
        ).fetchall()
    ]

    if raw_ids:
        placeholders = ",".join("?" * len(raw_ids))

        # 2. Find canonical transactions with primary_raw_id in those raw IDs
        canonical_ids = [
            r[0] for r in conn.execute(
                f"SELECT id FROM transactions WHERE primary_raw_id IN ({placeholders})",
                raw_ids
            ).fetchall()
        ]

        if canonical_ids:
            c_ph = ",".join("?" * len(canonical_ids))
            # 3. Delete dedup_links referencing those canonicals or raw IDs
            conn.execute(
                f"DELETE FROM dedup_links WHERE canonical_txn_id IN ({c_ph})",
                canonical_ids
            )

        # 4. Also delete dedup_links where raw_txn_id is in our raw_ids
        conn.execute(
            f"DELETE FROM dedup_links WHERE raw_txn_id IN ({placeholders})",
            raw_ids
        )

        if canonical_ids:
            c_ph = ",".join("?" * len(canonical_ids))
            # 5. Delete canonical transactions
            conn.execute(
                f"DELETE FROM transactions WHERE id IN ({c_ph})",
                canonical_ids
            )

        # 6. Delete raw transactions
        conn.execute(
            f"DELETE FROM raw_transactions WHERE id IN ({placeholders})",
            raw_ids
        )

    # 7. Delete imported_file record
    conn.execute("DELETE FROM imported_files WHERE id=?", (file_id,))
    conn.commit()

    success(f"已删除文件 ID={file_id}（{raw_count} 条原始记录）")
    info("请运行 [cyan]mz dedupe --month <月份>[/cyan] 重新计算账单统计")
    conn.close()
