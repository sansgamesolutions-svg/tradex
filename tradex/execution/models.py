from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Side = Literal["BUY", "SELL"]
AssetType = Literal["STOCK", "FOREX", "CRYPTO"]
OrderType = Literal["MARKET", "LIMIT"]
TimeInForce = Literal["DAY", "GTC"]


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
        symbol = self.symbol.strip().upper()
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
        if asset_type == "FOREX" and len(symbol.replace("/", "")) != 6:
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
    order_id: str
    status: str
    symbol: str
    side: Side
    quantity: float
    filled: float
    remaining: float
    average_fill_price: float
    broker: str


@dataclass(frozen=True)
class OrderPreview:
    platform: str
    venue: str
    symbol: str
    side: Side
    quantity: float
    order_type: OrderType
    limit_price: float | None = None
