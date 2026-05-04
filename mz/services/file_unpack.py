from __future__ import annotations

import shutil
import tempfile
import zipfile
from dataclasses import dataclass
from pathlib import Path

import pypdf

from mz.services.password_hints import get_hint


@dataclass
class UnpackedFile:
    path: Path
    original_name: str
    format: str
    is_temp: bool
    was_encrypted: bool


class PasswordRequired(Exception):
    def __init__(self, file_path: Path, hint: str):
        self.file_path = file_path
        self.hint = hint
        super().__init__(f"Password required for {file_path.name}: {hint}")


SUPPORTED_FORMATS = {".csv", ".xlsx", ".xls", ".pdf", ".zip"}


class FileUnpacker:
    def __init__(self, tmp_dir: Path | None = None):
        if tmp_dir is None:
            tmp_dir = Path.home() / ".mz" / "tmp"
        self.tmp_dir = tmp_dir
        self.tmp_dir.mkdir(parents=True, exist_ok=True)

    def unpack(
        self, file_path: Path, password: str | None = None
    ) -> list[UnpackedFile]:
        suffix = file_path.suffix.lower()
        if suffix not in SUPPORTED_FORMATS:
            raise ValueError(f"不支持的文件格式: {suffix}（支持: {', '.join(SUPPORTED_FORMATS)}）")

        if suffix == ".zip":
            return self._unpack_zip(file_path, password)
        if suffix == ".pdf":
            return self._unpack_pdf(file_path, password)
        # xlsx / csv — return as-is
        return [
            UnpackedFile(
                path=file_path,
                original_name=file_path.name,
                format=suffix.lstrip("."),
                is_temp=False,
                was_encrypted=False,
            )
        ]

    # ── ZIP ──────────────────────────────────────────────────────────────
    def _unpack_zip(self, zip_path: Path, password: str | None) -> list[UnpackedFile]:
        with zipfile.ZipFile(zip_path) as zf:
            needs_pwd = self._zip_needs_password(zf)
            if needs_pwd and password is None:
                raise PasswordRequired(zip_path, get_hint(zip_path))

            pwd_bytes = password.encode("utf-8") if password else None
            dest = Path(tempfile.mkdtemp(dir=self.tmp_dir))
            try:
                zf.extractall(path=dest, pwd=pwd_bytes)
            except RuntimeError as e:
                raise ValueError(f"ZIP 解压失败（密码错误？）: {e}") from e

        result = []
        for extracted in dest.rglob("*"):
            if extracted.is_file() and extracted.suffix.lower() in SUPPORTED_FORMATS - {".zip"}:
                result.append(
                    UnpackedFile(
                        path=extracted,
                        original_name=extracted.name,
                        format=extracted.suffix.lower().lstrip("."),
                        is_temp=True,
                        was_encrypted=needs_pwd,
                    )
                )
        return result

    @staticmethod
    def _zip_needs_password(zf: zipfile.ZipFile) -> bool:
        for info in zf.infolist():
            if info.flag_bits & 0x1:  # encryption flag
                return True
        return False

    # ── PDF ──────────────────────────────────────────────────────────────
    def _unpack_pdf(self, pdf_path: Path, password: str | None) -> list[UnpackedFile]:
        try:
            reader = pypdf.PdfReader(str(pdf_path))
        except Exception as e:
            raise ValueError(f"无法读取 PDF: {e}") from e

        if not reader.is_encrypted:
            return [
                UnpackedFile(
                    path=pdf_path,
                    original_name=pdf_path.name,
                    format="pdf",
                    is_temp=False,
                    was_encrypted=False,
                )
            ]

        if password is None:
            raise PasswordRequired(pdf_path, get_hint(pdf_path))

        rc = reader.decrypt(password)
        if rc.value == 0:
            raise ValueError("PDF 密码错误，解密失败。")

        out_path = self.tmp_dir / f"decrypted_{pdf_path.stem}.pdf"
        writer = pypdf.PdfWriter()
        for page in reader.pages:
            writer.add_page(page)
        with open(out_path, "wb") as f:
            writer.write(f)

        return [
            UnpackedFile(
                path=out_path,
                original_name=pdf_path.name,
                format="pdf",
                is_temp=True,
                was_encrypted=True,
            )
        ]

    def cleanup(self) -> None:
        """Remove all temp files."""
        if self.tmp_dir.exists():
            shutil.rmtree(self.tmp_dir, ignore_errors=True)
            self.tmp_dir.mkdir(parents=True, exist_ok=True)
