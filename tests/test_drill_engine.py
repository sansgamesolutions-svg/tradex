from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from tradex.drill.engine import DrillEngine
from tradex.drill.store import DrillStore
from tradex.drill.types import EASTERN, DrillConfig, PriceQuote, SignalDecision


def at(hour: int, minute: int) -> datetime:
    return datetime(2026, 6, 12, hour, minute, tzinfo=EASTERN).astimezone(UTC)


class FakeMarketData:
    def __init__(self, prices=None):
        self.prices = prices or {
            ("STOCK", "AAPL"): 100.0,
            ("CRYPTO", "BTC/USD"): 100.0,
        }
        self.failures: dict[tuple[str, str], int] = {}

    def fetch_daily(self, portfolio, symbol, cutoff):
        index = pd.date_range("2023-01-01", periods=720, freq="D", tz="UTC")
        return pd.DataFrame(
            {
                "open": 100.0,
                "high": 101.0,
                "low": 99.0,
                "close": 100.0,
                "volume": 1_000_000.0,
            },
            index=index,
        )

    def fetch_quote(self, portfolio, symbol, captured_at):
        key = (portfolio, symbol)
        if self.failures.get(key, 0):
            self.failures[key] -= 1
            raise ValueError("temporary feed failure")
        period_end = captured_at.astimezone(UTC).replace(second=0, microsecond=0)
        return PriceQuote(
            symbol=symbol,
            portfolio=portfolio,
            price=self.prices[key],
            source="fixture:5m",
            source_timestamp=period_end,
            period_start=period_end - timedelta(minutes=5),
            period_end=period_end,
            captured_at=captured_at,
        )

    def close(self):
        pass


class BuySignals:
    def __init__(self):
        self.calls: dict[tuple[str, str], int] = {}

    def decide(self, drill_id, config, portfolio, symbol, decided_at):
        key = (portfolio, symbol)
        self.calls[key] = self.calls.get(key, 0) + 1
        return SignalDecision(
            symbol=symbol,
            portfolio=portfolio,
            signal="BUY",
            source="TA_ONLY",
            decided_at=decided_at,
            ta_probability=0.8,
            fused_probability=0.8,
            confidence=0.6,
            threshold_used=0.65,
            policy_version="2.0",
            confirmation_details={"bullish_confirmed": True},
            reason="fixture",
        )


def make_engine(tmp_path, market=None, config=None):
    store = DrillStore(tmp_path / "drill.sqlite3")
    config = config or DrillConfig(
        session_date=date(2026, 6, 12),
        stock_symbols=("AAPL",),
        crypto_symbols=("BTC/USD",),
    )
    drill_id = store.create_drill(config)
    store.set_status(drill_id, "PREPARED")
    engine = DrillEngine(store=store, market_data=market or FakeMarketData())
    engine.signals = BuySignals()
    return engine, drill_id, config


def test_same_bar_cannot_fill_and_next_completed_bar_can(tmp_path):
    engine, drill_id, config = make_engine(tmp_path)

    engine.run_cycle(drill_id, at(9, 35))
    assert engine.store.open_positions(drill_id) == []
    assert len(engine.store.pending_orders(drill_id)) == 2

    engine.run_cycle(drill_id, at(9, 40))
    positions = engine.store.open_positions(drill_id)
    assert len(positions) == 2
    for fill in engine.store.table("fills", drill_id):
        assert fill["fill_price"] * fill["quantity"] + fill["fee"] <= (
            config.max_position_cost + 1e-6
        )


def test_completed_symbols_are_not_reevaluated(tmp_path):
    engine, drill_id, _ = make_engine(tmp_path)
    signals = engine.signals

    engine.run_cycle(drill_id, at(9, 35))
    engine.run_cycle(drill_id, at(9, 40))

    assert all(count == 1 for count in signals.calls.values())
    assert {item["state"] for item in engine.store.entry_states(drill_id)} == {"ORDER_CREATED"}


def test_transient_quote_failure_retries_only_unresolved_symbol(tmp_path):
    market = FakeMarketData()
    market.failures[("STOCK", "AAPL")] = 1
    engine, drill_id, _ = make_engine(tmp_path, market)

    engine.run_cycle(drill_id, at(9, 35))
    states = {
        (item["portfolio"], item["symbol"]): item for item in engine.store.entry_states(drill_id)
    }
    assert states[("STOCK", "AAPL")]["state"] == "PENDING"
    assert states[("CRYPTO", "BTC/USD")]["state"] == "ORDER_CREATED"

    engine.run_cycle(drill_id, at(9, 40))
    states = {
        (item["portfolio"], item["symbol"]): item for item in engine.store.entry_states(drill_id)
    }
    assert states[("STOCK", "AAPL")]["state"] == "ORDER_CREATED"
    assert engine.signals.calls[("CRYPTO", "BTC/USD")] == 1


def test_symbol_disables_after_three_failures_and_low_coverage_halts(tmp_path):
    market = FakeMarketData()
    market.fetch_quote = lambda *args, **kwargs: (_ for _ in ()).throw(
        ValueError("feed unavailable")
    )
    engine, drill_id, _ = make_engine(tmp_path, market)

    for minute in (30, 35, 40):
        engine.run_cycle(drill_id, at(9, minute))

    assert all(item["disabled"] for item in engine.store.symbol_health(drill_id))
    assert all(item["halted"] for item in engine.store.portfolios(drill_id))


def test_invalid_quotes_are_rejected(tmp_path):
    for price in (0.0, -1.0, float("nan")):
        market = FakeMarketData({("STOCK", "AAPL"): price, ("CRYPTO", "BTC/USD"): price})
        engine, drill_id, _ = make_engine(tmp_path / str(price), market)
        engine.run_cycle(drill_id, at(9, 35))
        assert engine.store.table("orders", drill_id) == []


def test_stop_and_session_close_orders_wait_for_later_bar(tmp_path):
    market = FakeMarketData()
    engine, drill_id, _ = make_engine(tmp_path, market)
    engine.run_cycle(drill_id, at(9, 35))
    engine.run_cycle(drill_id, at(9, 40))

    market.prices = {key: 98.0 for key in market.prices}
    engine.run_cycle(drill_id, at(9, 45))
    assert len(engine.store.open_positions(drill_id)) == 2
    engine.run_cycle(drill_id, at(9, 50))
    assert engine.store.open_positions(drill_id) == []
    assert all(item["close_reason"] == "STOP_LOSS" for item in engine.store.positions(drill_id))
