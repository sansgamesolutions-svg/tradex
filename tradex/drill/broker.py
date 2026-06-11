from __future__ import annotations

from collections.abc import Callable

from tradex.execution.models import (
    AssetType,
    OrderPreview,
    OrderRequest,
    OrderResult,
)

FillHandler = Callable[[OrderRequest], OrderResult]


class SimulatedBroker:
    """In-process broker that cannot route an order to an external venue."""

    name = "simulation"
    supported_asset_types: frozenset[AssetType] = frozenset(("STOCK", "CRYPTO"))

    def __init__(self, fill_handler: FillHandler | None = None) -> None:
        self.fill_handler = fill_handler

    def preview(self, request: OrderRequest) -> OrderPreview:
        return OrderPreview(
            platform=self.name,
            venue="internal-paper-ledger",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
            limit_price=request.limit_price,
        )

    def submit(self, request: OrderRequest) -> OrderResult:
        if self.fill_handler is None:
            raise RuntimeError("SimulatedBroker requires an internal fill handler")
        return self.fill_handler(request)

    def close(self) -> None:
        return None
