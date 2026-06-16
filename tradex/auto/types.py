from __future__ import annotations

from dataclasses import asdict, dataclass, field
from datetime import date, datetime, time
from typing import Literal

from tradex.config.settings import settings
from tradex.drill.types import EASTERN, DrillConfig, PortfolioKind
from tradex.strategy.schema import StrategyConfig

ExecutionMode = Literal["SIMULATED", "BROKER_PAPER", "BROKER_LIVE"]
RunStatus = Literal[
    "CREATED",
    "PREPARED",
    "RUNNING",
    "HALTED",
    "COMPLETED",
    "COMPLETED_NO_RUN",
    "EXPIRED",
    "FAILED",
]


@dataclass(frozen=True)
class RiskLimits:
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


@dataclass(frozen=True)
class BrokerRoute:
    portfolio: PortfolioKind
    platform: str
    mode: ExecutionMode = "SIMULATED"


@dataclass(frozen=True)
class MarketSession:
    opens_at: time = time(9, 30)
    entries_at: time = time(9, 35)
    entry_retry_deadline: time = time(10, 0)
    stop_entries_at: time = time(15, 50)
    force_close_at: time = time(15, 55)
    ends_at: time = time(16, 0)
    timezone: str = "America/New_York"

    def at(self, session_date: date, value: time) -> datetime:
        return datetime.combine(session_date, value, tzinfo=EASTERN)


@dataclass(frozen=True)
class SchedulerHealth:
    running: bool
    scheduler_heartbeat_at: str | None = None
    last_cycle_at: str | None = None
    market_phase: str = "UNKNOWN"


@dataclass(frozen=True)
class TradingRun:
    id: int
    session_date: str
    status: RunStatus
    profile_name: str
    profile_version: str
    execution_mode: ExecutionMode
    expired_reason: str = ""


@dataclass(frozen=True)
class AutoTradingConfig:
    data_dir: str = "data/drill"
    default_profile: str = "one-day-drill"
    worker_enabled: bool = True


@dataclass(frozen=True)
class TradingProfile:
    name: str
    version: str
    description: str
    stock_symbols: tuple[str, ...]
    crypto_symbols: tuple[str, ...]
    risk: RiskLimits = field(default_factory=RiskLimits)
    session: MarketSession = field(default_factory=MarketSession)
    execution_mode: ExecutionMode = "SIMULATED"
    broker_routes: tuple[BrokerRoute, ...] = (
        BrokerRoute("STOCK", "simulation"),
        BrokerRoute("CRYPTO", "simulation"),
    )
    model_name: str = "xgboost"
    strategy: StrategyConfig = field(default_factory=StrategyConfig.default)

    def to_drill_config(self, session_date: date) -> DrillConfig:
        return DrillConfig(
            session_date=session_date,
            stock_symbols=self.stock_symbols,
            crypto_symbols=self.crypto_symbols,
            initial_capital=self.risk.initial_capital,
            max_position_cost=self.risk.max_position_cost,
            max_open_positions=self.risk.max_open_positions,
            stop_loss_rate=self.risk.stop_loss_rate,
            take_profit_rate=self.risk.take_profit_rate,
            max_drawdown_rate=self.risk.max_drawdown_rate,
            max_price_age_minutes=self.risk.max_price_age_minutes,
            max_future_seconds=self.risk.max_future_seconds,
            min_quote_coverage=self.risk.min_quote_coverage,
            max_symbol_failures=self.risk.max_symbol_failures,
            model_name=self.model_name,
            ml_ta_signal_threshold=self.strategy.ml_ta_threshold,
            ta_only_signal_threshold=self.strategy.ta_only_threshold,
            decision_policy_version=str(settings.decision_policy_version),
        )

    def to_dict(self) -> dict:
        return asdict(self)
