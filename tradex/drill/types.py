from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from typing import Literal
from zoneinfo import ZoneInfo

from tradex.config.settings import settings

PortfolioKind = Literal["STOCK", "CRYPTO"]
DrillStatus = Literal[
    "CREATED",
    "PREPARED",
    "RUNNING",
    "HALTED",
    "COMPLETED",
    "COMPLETED_NO_RUN",
    "EXPIRED",
    "FAILED",
]
SignalValue = Literal["BUY", "SELL", "HOLD"]

EASTERN = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class DrillConfig:
    session_date: date
    stock_symbols: tuple[str, ...] = ("SPY", "QQQ", "AAPL", "MSFT", "NVDA")
    crypto_symbols: tuple[str, ...] = (
        "BTC/USD",
        "ETH/USD",
        "SOL/USD",
        "XRP/USD",
        "ADA/USD",
    )
    initial_capital: float = 5_000.0
    max_position_cost: float = 500.0
    max_open_positions: int = 2
    stop_loss_rate: float = 0.01
    take_profit_rate: float = 0.02
    max_drawdown_rate: float = 0.01
    max_price_age_minutes: int = 10
    max_future_seconds: int = 60
    min_quote_coverage: float = 0.60
    max_symbol_failures: int = 3
    stock_slippage_rate: float = 0.0002
    stock_fixed_fee: float = 0.35
    crypto_slippage_rate: float = 0.0005
    crypto_fee_rate: float = 0.004
    model_name: str = "xgboost"
    ml_ta_signal_threshold: float = 0.55
    ta_only_signal_threshold: float = 0.65
    decision_policy_version: str = "2.0"

    @classmethod
    def from_settings(cls, session_date: date) -> DrillConfig:
        return cls(
            session_date=session_date,
            initial_capital=float(settings.drill_initial_capital),
            max_position_cost=float(settings.drill_max_position_cost),
            max_open_positions=int(settings.drill_max_open_positions),
            stop_loss_rate=float(settings.drill_stop_loss_rate),
            take_profit_rate=float(settings.drill_take_profit_rate),
            max_drawdown_rate=float(settings.drill_max_drawdown_rate),
            max_price_age_minutes=int(settings.drill_max_price_age_minutes),
            max_future_seconds=int(settings.drill_max_future_seconds),
            min_quote_coverage=float(settings.drill_min_quote_coverage),
            max_symbol_failures=int(settings.drill_max_symbol_failures),
            stock_slippage_rate=float(settings.drill_stock_slippage_rate),
            stock_fixed_fee=float(settings.drill_stock_fixed_fee),
            crypto_slippage_rate=float(settings.drill_crypto_slippage_rate),
            crypto_fee_rate=float(settings.drill_crypto_fee_rate),
            ml_ta_signal_threshold=float(settings.signal_threshold),
            ta_only_signal_threshold=float(settings.ta_only_signal_threshold),
            decision_policy_version=str(settings.decision_policy_version),
        )

    def at(self, value: time) -> datetime:
        return datetime.combine(self.session_date, value, tzinfo=EASTERN)

    @property
    def prepare_at(self) -> datetime:
        return self.at(time(9, 20))

    @property
    def opens_at(self) -> datetime:
        return self.at(time(9, 30))

    @property
    def entries_at(self) -> datetime:
        return self.at(time(9, 35))

    @property
    def stop_entries_at(self) -> datetime:
        return self.at(time(15, 50))

    @property
    def entry_retry_deadline(self) -> datetime:
        return self.at(time(10, 0))

    @property
    def force_close_at(self) -> datetime:
        return self.at(time(15, 55))

    @property
    def ends_at(self) -> datetime:
        return self.at(time(16, 0))

    def to_dict(self) -> dict:
        payload = asdict(self)
        payload["session_date"] = self.session_date.isoformat()
        return payload


@dataclass(frozen=True)
class PriceQuote:
    symbol: str
    portfolio: PortfolioKind
    price: float
    source: str
    source_timestamp: datetime
    period_start: datetime
    period_end: datetime
    captured_at: datetime


@dataclass(frozen=True)
class SignalDecision:
    symbol: str
    portfolio: PortfolioKind
    signal: SignalValue
    source: str
    decided_at: datetime
    ml_probability: float | None = None
    ta_probability: float | None = None
    fused_probability: float = 0.5
    confidence: float = 0.0
    threshold_used: float = 0.5
    policy_version: str = ""
    confirmation_details: dict[str, bool] = field(default_factory=dict)
    reason: str = ""


@dataclass(frozen=True)
class RiskDecision:
    accepted: bool
    reason: str
    quantity: float = 0.0
    estimated_all_in_cost: float = 0.0


@dataclass(frozen=True)
class CostModel:
    slippage_rate: float
    fee_rate: float = 0.0
    fixed_fee: float = 0.0

    def fill_price(self, market_price: float, side: str) -> float:
        direction = 1 if side == "BUY" else -1
        return market_price * (1 + direction * self.slippage_rate)

    def fee(self, notional: float) -> float:
        return self.fixed_fee + notional * self.fee_rate


@dataclass(frozen=True)
class PortfolioView:
    kind: PortfolioKind
    cash: float
    equity: float
    realized_pnl: float
    unrealized_pnl: float
    fees: float
    slippage: float
    open_positions: int
    halted: bool
    data_failures: int


@dataclass(frozen=True)
class DrillReport:
    drill_id: int
    session_date: str
    status: str
    generated_at: str
    portfolios: tuple[dict, ...]
    combined: dict
    signals: tuple[dict, ...] = field(default_factory=tuple)
    positions: tuple[dict, ...] = field(default_factory=tuple)
    events: tuple[dict, ...] = field(default_factory=tuple)
    equity_curve: tuple[dict, ...] = field(default_factory=tuple)
    recommendations: tuple[dict, ...] = field(default_factory=tuple)

    def to_dict(self) -> dict:
        return asdict(self)
