from __future__ import annotations

from tradex.auto.types import RiskLimits, TradingProfile
from tradex.strategy.schema import StrategyConfig


def one_day_drill_profile() -> TradingProfile:
    strategy = StrategyConfig.default()
    return TradingProfile(
        name="one-day-drill",
        version="1.0",
        description="Internal one-day paper trading drill with simulated execution only.",
        stock_symbols=("SPY", "QQQ", "AAPL", "MSFT", "NVDA"),
        crypto_symbols=("BTC/USD", "ETH/USD", "SOL/USD", "XRP/USD", "ADA/USD"),
        risk=RiskLimits(),
        execution_mode="SIMULATED",
        model_name="xgboost",
        strategy=strategy,
    )


def stocks_only_week_drill_profile() -> TradingProfile:
    strategy = StrategyConfig.default()
    return TradingProfile(
        name="stocks-only-week-drill",
        version="1.0",
        description="Remaining-week paper drill for the stock watchlist only.",
        stock_symbols=("SPY", "QQQ", "AAPL", "MSFT", "NVDA"),
        crypto_symbols=(),
        risk=RiskLimits(),
        execution_mode="SIMULATED",
        model_name="xgboost",
        strategy=strategy,
    )


def available_profiles() -> dict[str, TradingProfile]:
    profiles = (one_day_drill_profile(), stocks_only_week_drill_profile())
    return {profile.name: profile for profile in profiles}


def get_profile(name: str = "one-day-drill") -> TradingProfile:
    normalized = name.strip().lower()
    profiles = available_profiles()
    try:
        return profiles[normalized]
    except KeyError as exc:
        available = ", ".join(sorted(profiles))
        raise ValueError(
            f"Unknown auto trading profile {name}. Available profiles: {available}"
        ) from exc
