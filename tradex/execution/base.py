from __future__ import annotations

from typing import Protocol

from tradex.execution.models import AssetType, OrderPreview, OrderRequest, OrderResult


class TradingPlatform(Protocol):
    """Common contract implemented by every trading platform adapter."""

    name: str
    supported_asset_types: frozenset[AssetType]

    def preview(self, request: OrderRequest) -> OrderPreview: ...

    def submit(self, request: OrderRequest) -> OrderResult: ...

    def close(self) -> None: ...
