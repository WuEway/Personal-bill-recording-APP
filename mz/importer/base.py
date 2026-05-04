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
