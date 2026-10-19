"""Local file cache for SEC responses.

Filings never change once accepted (corrections arrive as new amendment filings), so filing
documents are cached permanently. Indexes such as the ticker list and submissions history
change over time and are cached with a time-to-live.
"""

from __future__ import annotations

import os
import time
from pathlib import Path


class FileCache:
    def __init__(self, root: Path) -> None:
        self.root = root

    def path(self, key: str) -> Path:
        return self.root / key

    def get(self, key: str, max_age_seconds: float | None = None) -> bytes | None:
        path = self.path(key)
        if not path.exists():
            return None
        if max_age_seconds is not None and time.time() - path.stat().st_mtime > max_age_seconds:
            return None
        return path.read_bytes()

    def put(self, key: str, data: bytes) -> None:
        path = self.path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_bytes(data)
        os.replace(tmp, path)
