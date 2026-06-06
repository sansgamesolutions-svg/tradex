from __future__ import annotations

from pathlib import Path

from tradex.storage.base import Storage


class LocalStorage(Storage):
    """Filesystem-backed storage. Keys are relative paths under *base_dir*."""

    def __init__(self, base_dir: Path):
        self.base_dir = base_dir

    def _resolve(self, key: str) -> Path:
        p = self.base_dir / key
        p.parent.mkdir(parents=True, exist_ok=True)
        return p

    def get(self, key: str) -> bytes | None:
        p = self._resolve(key)
        return p.read_bytes() if p.exists() else None

    def put(self, key: str, data: bytes) -> None:
        self._resolve(key).write_bytes(data)

    def exists(self, key: str) -> bool:
        return (self.base_dir / key).exists()
