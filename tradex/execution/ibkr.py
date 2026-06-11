from __future__ import annotations

from dataclasses import dataclass
from typing import Any, Protocol

from ib_async import IB, Forex, LimitOrder, MarketOrder, Stock

from tradex.config.settings import settings
from tradex.execution.models import OrderRequest, OrderResult


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
        if request.asset_type == "CRYPTO":
            raise ValueError("CRYPTO orders must use Kraken")
        if request.asset_type == "STOCK":
            return Stock(
                request.symbol,
                request.exchange or "SMART",
                request.currency,
            )
        return Forex(
            request.symbol.replace("/", ""),
            exchange=request.exchange or "IDEALPRO",
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
            order_id=str(trade.order.orderId),
            status=status.status,
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled=float(status.filled),
            remaining=float(status.remaining),
            average_fill_price=float(status.avgFillPrice),
            broker="IBKR",
        )

    def buy(self, symbol: str, quantity: float, **kwargs: Any) -> OrderResult:
        return self.submit(OrderRequest(symbol=symbol, side="BUY", quantity=quantity, **kwargs))

    def sell(self, symbol: str, quantity: float, **kwargs: Any) -> OrderResult:
        return self.submit(OrderRequest(symbol=symbol, side="SELL", quantity=quantity, **kwargs))
