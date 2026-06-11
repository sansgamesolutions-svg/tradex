from __future__ import annotations

from datetime import UTC, date, datetime, timedelta

import pandas as pd

from tradex.drill.engine import DrillEngine
from tradex.drill.store import DrillStore
from tradex.drill.types import EASTERN, DrillConfig, PriceQuote, SignalDecision


class FakeMarketData:
    def __init__(self, prices=None, *, stale=False):
        self.prices = prices or {
            ("STOCK", "AAPL"): 100.0,
            ("CRYPTO", "BTC/USD"): 100.0,
        }
        self.stale = stale
        self.closed = False

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
        timestamp = captured_at - timedelta(minutes=11) if self.stale else captured_at
        return PriceQuote(
            symbol=symbol,
            portfolio=portfolio,
            price=self.prices[(portfolio, symbol)],
            source="fixture:5m",
            source_timestamp=timestamp,
            captured_at=captured_at,
        )

    def close(self):
        self.closed = True


class BuySignals:
    def decide(self, drill_id, config, portfolio, symbol, decided_at):
        return SignalDecision(
            symbol=symbol,
            portfolio=portfolio,
            signal="BUY",
            source="TA_ONLY",
            decided_at=decided_at,
            ta_probability=0.8,
            reason="fixture",
        )


class HoldSignals(BuySignals):
    def decide(self, drill_id, config, portfolio, symbol, decided_at):
        decision = super().decide(drill_id, config, portfolio, symbol, decided_at)
        return SignalDecision(
            **{
                **decision.__dict__,
                "signal": "HOLD",
                "ta_probability": 0.5,
            }
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


def at(hour, minute):
    return datetime(2026, 6, 12, hour, minute, tzinfo=EASTERN).astimezone(UTC)


def test_entry_cycle_caps_cost_and_is_idempotent(tmp_path):
    engine, drill_id, config = make_engine(tmp_path)

    engine.run_cycle(drill_id, at(9, 35))
    engine.run_cycle(drill_id, at(9, 35))

    positions = engine.store.open_positions(drill_id)
    assert len(positions) == 2
    assert {position["portfolio"] for position in positions} == {"STOCK", "CRYPTO"}
    assert len(engine.store.table("orders", drill_id)) == 2

    fills = engine.store.table("fills", drill_id)
    for fill in fills:
        all_in = fill["fill_price"] * fill["quantity"] + fill["fee"]
        assert all_in <= config.max_position_cost + 1e-6


def test_stale_prices_produce_rejections_without_trades(tmp_path):
    engine, drill_id, _ = make_engine(tmp_path, FakeMarketData(stale=True))

    engine.run_cycle(drill_id, at(9, 35))

    assert engine.store.open_positions(drill_id) == []
    messages = [event["message"] for event in engine.store.table("events", drill_id)]
    assert any("price is stale" in message for message in messages)


def test_stop_loss_closes_position_and_disables_reentry(tmp_path):
    market = FakeMarketData()
    engine, drill_id, _ = make_engine(tmp_path, market)
    engine.run_cycle(drill_id, at(9, 35))

    market.prices[("STOCK", "AAPL")] = 98.0
    market.prices[("CRYPTO", "BTC/USD")] = 98.0
    engine.run_cycle(drill_id, at(9, 40))

    assert engine.store.open_positions(drill_id) == []
    positions = engine.store.positions(drill_id)
    assert all(position["close_reason"] == "STOP_LOSS" for position in positions)
    assert all(position["realized_pnl"] < 0 for position in positions)


def test_take_profit_closes_position(tmp_path):
    market = FakeMarketData()
    engine, drill_id, _ = make_engine(tmp_path, market)
    engine.run_cycle(drill_id, at(9, 35))

    market.prices[("STOCK", "AAPL")] = 103.0
    market.prices[("CRYPTO", "BTC/USD")] = 103.0
    engine.run_cycle(drill_id, at(9, 40))

    positions = engine.store.positions(drill_id)
    assert all(position["close_reason"] == "TAKE_PROFIT" for position in positions)
    assert all(position["realized_pnl"] > 0 for position in positions)


def test_force_close_finishes_all_positions(tmp_path):
    engine, drill_id, _ = make_engine(tmp_path)
    engine.run_cycle(drill_id, at(9, 35))

    engine.run_cycle(drill_id, at(15, 55))

    assert engine.store.open_positions(drill_id) == []
    assert all(
        position["close_reason"] == "SESSION_CLOSE" for position in engine.store.positions(drill_id)
    )


def test_three_data_failure_cycles_halt_portfolios(tmp_path):
    market = FakeMarketData()
    engine, drill_id, _ = make_engine(tmp_path, market)

    def fail(*args, **kwargs):
        raise ValueError("feed unavailable")

    market.fetch_quote = fail
    for minute in (30, 35, 40):
        engine.run_cycle(drill_id, at(9, minute))

    assert all(item["halted"] for item in engine.store.portfolios(drill_id))


def test_position_limit_allows_only_two_entries(tmp_path):
    prices = {
        ("STOCK", "AAPL"): 100.0,
        ("STOCK", "MSFT"): 100.0,
        ("STOCK", "NVDA"): 100.0,
    }
    config = DrillConfig(
        session_date=date(2026, 6, 12),
        stock_symbols=("AAPL", "MSFT", "NVDA"),
        crypto_symbols=(),
    )
    engine, drill_id, _ = make_engine(tmp_path, FakeMarketData(prices), config)

    engine.run_cycle(drill_id, at(9, 35))

    assert len(engine.store.open_positions(drill_id, "STOCK")) == 2


def test_insufficient_cash_and_hold_signals_do_not_force_activity(tmp_path):
    config = DrillConfig(
        session_date=date(2026, 6, 12),
        stock_symbols=("AAPL",),
        crypto_symbols=(),
        initial_capital=100.0,
    )
    engine, drill_id, _ = make_engine(
        tmp_path,
        FakeMarketData({("STOCK", "AAPL"): 100.0}),
        config,
    )
    engine.run_cycle(drill_id, at(9, 35))
    assert engine.store.open_positions(drill_id) == []

    other_store = DrillStore(tmp_path / "hold.sqlite3")
    other_id = other_store.create_drill(
        DrillConfig(
            session_date=date(2026, 6, 12),
            stock_symbols=("AAPL",),
            crypto_symbols=(),
        )
    )
    other_store.set_status(other_id, "PREPARED")
    other = DrillEngine(
        store=other_store,
        market_data=FakeMarketData({("STOCK", "AAPL"): 100.0}),
    )
    other.signals = HoldSignals()
    other.run_cycle(other_id, at(9, 35))
    assert other.store.open_positions(other_id) == []
