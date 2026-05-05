from __future__ import annotations

import sqlite3
from dataclasses import dataclass
from pathlib import Path

from mz.importer import find_importer
from mz.repositories.account_repo import AccountRepository
from mz.repositories.imported_file_repo import ImportedFileRepository
from mz.repositories.raw_txn_repo import RawTransactionRepository
from mz.services.account_resolver import AccountResolver
from mz.services.file_unpack import FileUnpacker, PasswordRequired
from mz.services.transfer_detector import TransferDetector
from mz.utils.hashing import sha256_of


@dataclass
class ImportResult:
    skipped_duplicate: bool = False
    file_id: int | None = None
    rows_parsed: int = 0
    rows_inserted: int = 0
    rows_duplicate: int = 0
    internal_transfers_detected: int = 0
    source: str = ""
    period_start: str = ""
    period_end: str = ""
    account_label: str | None = None


class ImportService:
    def __init__(self, conn: sqlite3.Connection, user_name: str | None = None):
        self.conn = conn
        self.raw_repo = RawTransactionRepository(conn)
        self.file_repo = ImportedFileRepository(conn)
        self.acc_repo = AccountRepository(conn)
        self.resolver = AccountResolver(self.acc_repo)
        self.transfer_detector = TransferDetector(user_name)
        self.unpacker = FileUnpacker()

    def import_file(
        self,
        file_path: Path,
        password: str | None = None,
        source_hint: str | None = None,
        password_callback=None,  # callable(file_path, hint) -> str
        account_label: str | None = None,  # user-supplied last-4 override
    ) -> list[ImportResult]:
        """
        Unpack, detect format, parse, and insert raw transactions.
        Returns one ImportResult per sub-file processed.
        """
        file_hash = sha256_of(file_path)
        existing_id = self.file_repo.get_id_by_hash(file_hash)
        if existing_id is not None:
            # File already imported. If caller supplied an account_label,
            # update it on the existing record instead of skipping silently.
            if account_label:
                self.file_repo.update_account_label(existing_id, account_label)
                return [ImportResult(
                    skipped_duplicate=True,
                    file_id=existing_id,
                    account_label=account_label,
                )]
            return [ImportResult(skipped_duplicate=True)]

        try:
            unpacked_files = self.unpacker.unpack(file_path, password=password)
        except PasswordRequired as e:
            if password_callback:
                pwd = password_callback(e.file_path, e.hint)
                unpacked_files = self.unpacker.unpack(file_path, password=pwd)
            else:
                raise

        results = []
        for unpacked in unpacked_files:
            result = self._process_file(
                unpacked, file_hash, source_hint, file_path, account_label
            )
            results.append(result)
            # Clean up temp files immediately
            if unpacked.is_temp:
                unpacked.path.unlink(missing_ok=True)

        return results

    def _process_file(
        self, unpacked, file_hash, source_hint, original_path,
        account_label: str | None = None,
    ) -> ImportResult:
        result = ImportResult()
        try:
            importer = find_importer(unpacked.path, unpacked.format, hint=source_hint)
        except ValueError as e:
            raise ValueError(str(e)) from e

        result.source = importer.SOURCE_NAME

        try:
            period = importer.detect_period(unpacked.path, unpacked.format)
            result.period_start = period[0].isoformat()
            result.period_end = period[1].isoformat()
        except Exception:
            period = (None, None)

        # Resolve account_label: user override > auto-extract from file
        resolved_label = account_label
        if not resolved_label and importer.SOURCE_NAME.startswith("bank_"):
            try:
                resolved_label = importer.extract_account_label(
                    unpacked.path, unpacked.format
                )
            except Exception:
                pass

        file_id = self.file_repo.create(
            source=importer.SOURCE_NAME,
            file_path=str(original_path),
            file_hash=file_hash,
            file_format=unpacked.format,
            is_encrypted=unpacked.was_encrypted,
            period_start=period[0],
            period_end=period[1],
            account_label=resolved_label,
        )
        result.account_label = resolved_label
        result.file_id = file_id

        for draft in importer.parse(unpacked.path, unpacked.format):
            result.rows_parsed += 1
            account_id = self.resolver.resolve(draft.payment_method_raw, draft.source)
            raw_id = self.raw_repo.insert(draft, file_id, account_id)
            if raw_id is None:
                result.rows_duplicate += 1
                continue
            result.rows_inserted += 1

        self.file_repo.update_row_count(file_id, result.rows_inserted)

        # Detect internal transfers on newly inserted rows
        for raw in self.raw_repo.list_by_source_file(file_id):
            reason = self.transfer_detector.detect(raw)
            if reason:
                self.raw_repo.mark_internal_transfer(raw.id, reason)
                result.internal_transfers_detected += 1

        return result
