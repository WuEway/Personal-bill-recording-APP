from __future__ import annotations

from abc import ABC, abstractmethod
from datetime import date
from pathlib import Path
from typing import Iterator

from mz.models.transaction import RawTransactionDraft


class BaseImporter(ABC):
    SOURCE_NAME: str
    DISPLAY_NAME: str
    SUPPORTED_FORMATS: list[str]

    @abstractmethod
    def detect(self, file_path: Path, file_format: str) -> bool:
        """Return True if this importer can handle the file."""

    @abstractmethod
    def parse(self, file_path: Path, file_format: str) -> Iterator[RawTransactionDraft]:
        """Yield one RawTransactionDraft per transaction row."""

    @abstractmethod
    def detect_period(self, file_path: Path, file_format: str) -> tuple[date, date]:
        """Return (period_start, period_end) from file metadata."""

    def extract_account_label(self, file_path: Path, file_format: str) -> str | None:
        """
        Try to extract the last-4 digits of the account number from the file.
        Override in bank importers that can read this from the PDF header.
        Returns a 4-digit string or None.
        """
        return None
