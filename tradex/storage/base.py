from __future__ import annotations

from abc import ABC, abstractmethod


class Storage(ABC):
    @abstractmethod
    def get(self, key: str) -> bytes | None: ...

    @abstractmethod
    def put(self, key: str, data: bytes) -> None: ...

    @abstractmethod
    def exists(self, key: str) -> bool: ...
