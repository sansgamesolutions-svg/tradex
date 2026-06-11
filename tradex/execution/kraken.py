from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

import ccxt

from tradex.config.settings import settings
from tradex.execution.models import OrderRequest, OrderResult


class KrakenClient(Protocol):
    def load_markets(self) -> dict[str, Any]: ...

    def market(self, symbol: str) -> dict[str, Any]: ...

    def amount_to_precision(self, symbol: str, amount: float) -> str: ...

    def price_to_precision(self, symbol: str, price: float) -> str: ...

    def create_order(
        self,
        symbol: str,
        order_type: str,
        side: str,
        amount: float,
        price: float | None = None,
        params: dict[str, Any] | None = None,
    ) -> dict[str, Any]: ...

    def close(self) -> Any: ...


@dataclass(frozen=True)
class KrakenConfig:
    api_key: str = ""
    api_secret: str = ""
    timeout: int = 10_000

    @classmethod
    def from_settings(cls) -> KrakenConfig:
        return cls(
            api_key=settings.kraken_api_key,
            api_secret=settings.kraken_api_secret,
            timeout=int(settings.kraken_timeout),
        )


class KrakenBroker:
    """Submit spot cryptocurrency orders to Kraken through CCXT."""

    def __init__(
        self,
        config: KrakenConfig | None = None,
        client: KrakenClient | None = None,
    ) -> None:
        self.config = config or KrakenConfig.from_settings()
        self.client: KrakenClient = client or ccxt.kraken(
            {
                "apiKey": self.config.api_key,
                "secret": self.config.api_secret,
                "enableRateLimit": True,
                "timeout": self.config.timeout,
                "options": {"defaultType": "spot"},
            }
        )

    def __enter__(self) -> KrakenBroker:
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def close(self) -> None:
        self.client.close()

    def symbol_for(self, request: OrderRequest) -> str:
        symbol = request.symbol.replace("-", "/")
        if "/" in symbol:
            return symbol
        if symbol.endswith(request.currency) and len(symbol) > len(request.currency):
            base = symbol[: -len(request.currency)]
            return f"{base}/{request.currency}"
        return f"{symbol}/{request.currency}"

    def submit(self, request: OrderRequest) -> OrderResult:
        if request.asset_type != "CRYPTO":
            raise ValueError("Kraken only supports CRYPTO orders")
        if not self.config.api_key or not self.config.api_secret:
            raise ValueError(
                "Kraken credentials are required in TRADEX_KRAKEN_API_KEY "
                "and TRADEX_KRAKEN_API_SECRET"
            )

        symbol = self.symbol_for(request)
        self.client.load_markets()
        market = self.client.market(symbol)
        if not market.get("spot", True):
            raise ValueError(f"{symbol} is not a Kraken spot market")

        amount = float(self.client.amount_to_precision(symbol, request.quantity))
        price = None
        params: dict[str, Any] = {}
        if request.order_type == "LIMIT":
            price = float(self.client.price_to_precision(symbol, request.limit_price))
            params["timeInForce"] = "GTC"

        order = self.client.create_order(
            symbol,
            request.order_type.lower(),
            request.side.lower(),
            amount,
            price,
            params,
        )
        filled = float(order.get("filled") or 0.0)
        quantity = float(order.get("amount") or amount)
        remaining = order.get("remaining")
        if remaining is None:
            remaining = max(quantity - filled, 0.0)

        return OrderResult(
            order_id=str(order.get("id") or ""),
            status=str(order.get("status") or "submitted"),
            symbol=str(order.get("symbol") or symbol),
            side=request.side,
            quantity=quantity,
            filled=filled,
            remaining=float(remaining),
            average_fill_price=float(order.get("average") or 0.0),
            broker="KRAKEN",
        )

    def buy(self, symbol: str, quantity: float, **kwargs: Any) -> OrderResult:
        return self.submit(
            OrderRequest(
                symbol=symbol,
                side="BUY",
                quantity=quantity,
                asset_type="CRYPTO",
                **kwargs,
            )
        )

    def sell(self, symbol: str, quantity: float, **kwargs: Any) -> OrderResult:
        return self.submit(
            OrderRequest(
                symbol=symbol,
                side="SELL",
                quantity=quantity,
                asset_type="CRYPTO",
                **kwargs,
            )
        )
