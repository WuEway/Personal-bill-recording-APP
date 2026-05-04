from __future__ import annotations

import hashlib
from pathlib import Path


def sha256_of(file_path: Path, chunk_size: int = 65536) -> str:
    h = hashlib.sha256()
    with open(file_path, "rb") as f:
        while chunk := f.read(chunk_size):
            h.update(chunk)
    return h.hexdigest()
