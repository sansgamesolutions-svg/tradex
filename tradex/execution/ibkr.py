from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Any, Literal, Protocol

from ib_async import IB, Crypto, Forex, LimitOrder, MarketOrder, Stock

from tradex.config.settings import settings

Side = Literal["BUY", "SELL"]
AssetType = Literal["STOCK", "FOREX", "CRYPTO"]
OrderType = Literal["MARKET", "LIMIT"]
TimeInForce = Literal["DAY", "GTC"]


class IBClient(Protocol):
    def connect(self, *args: Any, **kwargs: Any) -> Any: ...

    def disconnect(self) -> Any: ...

    def isConnected(self) -> bool: ...

    def qualifyContracts(self, *contracts: Any) -> list[Any]: ...

    def placeOrder(self, contract: Any, order: Any) -> Any: ...


@dataclass(frozen=True)
class IBKRConfig:
    host: str = "127.0.0.1"
    port: int = 7497
    client_id: int = 10
    account: str = ""
    timeout: float = 4.0

    @classmethod
    def from_settings(cls) -> IBKRConfig:
        return cls(
            host=settings.ibkr_host,
            port=int(settings.ibkr_port),
            client_id=int(settings.ibkr_client_id),
            account=settings.ibkr_account,
            timeout=float(settings.ibkr_timeout),
        )


@dataclass(frozen=True)
class OrderRequest:
    symbol: str
    side: Side
    quantity: float
    asset_type: AssetType = "STOCK"
    order_type: OrderType = "MARKET"
    limit_price: float | None = None
    exchange: str | None = None
    currency: str = "USD"
    time_in_force: TimeInForce = "DAY"
    outside_rth: bool = False
    account: str = ""

    def __post_init__(self) -> None:
        symbol = self.symbol.replace("/", "").strip().upper()
        side = self.side.upper()
        asset_type = self.asset_type.upper()
        order_type = self.order_type.upper()
        currency = self.currency.strip().upper()
        time_in_force = self.time_in_force.upper()

        if not symbol:
            raise ValueError("symbol is required")
        if side not in {"BUY", "SELL"}:
            raise ValueError("side must be BUY or SELL")
        if asset_type not in {"STOCK", "FOREX", "CRYPTO"}:
            raise ValueError("asset_type must be STOCK, FOREX, or CRYPTO")
        if order_type not in {"MARKET", "LIMIT"}:
            raise ValueError("order_type must be MARKET or LIMIT")
        if not math.isfinite(self.quantity) or self.quantity <= 0:
            raise ValueError("quantity must be a positive finite number")
        if order_type == "LIMIT":
            if self.limit_price is None:
                raise ValueError("limit_price is required for LIMIT orders")
            if not math.isfinite(self.limit_price) or self.limit_price <= 0:
                raise ValueError("limit_price must be a positive finite number")
        elif self.limit_price is not None:
            raise ValueError("limit_price is only valid for LIMIT orders")
        if asset_type == "FOREX" and len(symbol) != 6:
            raise ValueError("FOREX symbols must be six-letter pairs such as EURUSD")
        if not currency:
            raise ValueError("currency is required")
        if time_in_force not in {"DAY", "GTC"}:
            raise ValueError("time_in_force must be DAY or GTC")

        object.__setattr__(self, "symbol", symbol)
        object.__setattr__(self, "side", side)
        object.__setattr__(self, "asset_type", asset_type)
        object.__setattr__(self, "order_type", order_type)
        object.__setattr__(self, "currency", currency)
        object.__setattr__(self, "time_in_force", time_in_force)
        if self.exchange:
            object.__setattr__(self, "exchange", self.exchange.strip().upper())


@dataclass(frozen=True)
class OrderResult:
    order_id: int
    status: str
    symbol: str
    side: Side
    quantity: float
    filled: float
    remaining: float
    average_fill_price: float


class IBKRBroker:
    """Submit validated orders to TWS or IB Gateway through ib_async."""

    def __init__(
        self,
        config: IBKRConfig | None = None,
        client: IBClient | None = None,
    ) -> None:
        self.config = config or IBKRConfig.from_settings()
        self.client: IBClient = client or IB()

    def connect(self) -> None:
        if self.client.isConnected():
            return
        self.client.connect(
            self.config.host,
            self.config.port,
            clientId=self.config.client_id,
            timeout=self.config.timeout,
            readonly=False,
            account=self.config.account,
        )

    def close(self) -> None:
        if self.client.isConnected():
            self.client.disconnect()

    def __enter__(self) -> IBKRBroker:
        self.connect()
        return self

    def __exit__(self, *_: Any) -> None:
        self.close()

    def build_contract(self, request: OrderRequest) -> Any:
        if request.asset_type == "STOCK":
            return Stock(
                request.symbol,
                request.exchange or "SMART",
                request.currency,
            )
        if request.asset_type == "FOREX":
            return Forex(request.symbol, exchange=request.exchange or "IDEALPRO")
        return Crypto(
            request.symbol,
            request.exchange or "PAXOS",
            request.currency,
        )

    def build_order(self, request: OrderRequest) -> Any:
        kwargs = {
            "tif": request.time_in_force,
            "outsideRth": request.outside_rth,
            "account": request.account or self.config.account,
        }
        if request.order_type == "LIMIT":
            return LimitOrder(
                request.side,
                request.quantity,
                request.limit_price,
                **kwargs,
            )
        return MarketOrder(request.side, request.quantity, **kwargs)

    def submit(self, request: OrderRequest) -> OrderResult:
        self.connect()
        contract = self.build_contract(request)
        qualified = self.client.qualifyContracts(contract)
        if not qualified:
            raise ValueError(
                f"IBKR could not resolve {request.asset_type} contract {request.symbol}"
            )

        trade = self.client.placeOrder(qualified[0], self.build_order(request))
        status = trade.orderStatus
        return OrderResult(
            order_id=int(trade.order.orderId),
            status=status.status,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled=float(status.filled),
            remaining=float(status.remaining),
            average_fill_price=float(status.avgFillPrice),
        )

    def buy(self, symbol: str, quantity: float, **kwargs: Any) -> OrderResult:
        return self.submit(OrderRequest(symbol=symbol, side="BUY", quantity=quantity, **kwargs))

    def sell(self, symbol: str, quantity: float, **kwargs: Any) -> OrderResult:
        return self.submit(OrderRequest(symbol=symbol, side="SELL", quantity=quantity, **kwargs))
