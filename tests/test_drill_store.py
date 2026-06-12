from __future__ import annotations

import sqlite3
from datetime import date, datetime

from tradex.drill.store import DrillStore
from tradex.drill.types import EASTERN, DrillConfig


def test_store_creates_isolated_portfolios_and_idempotent_orders(tmp_path):
    store = DrillStore(tmp_path / "drill.sqlite3")
    config = DrillConfig(session_date=date(2026, 6, 12))

    first = store.create_drill(config)
    second = store.create_drill(config)
    order_time = datetime(2026, 6, 12, 9, 35, tzinfo=EASTERN)
    order_one = store.create_order(
        first,
        "STOCK",
        "AAPL",
        "BUY",
        1.0,
        "ENTRY_SIGNAL",
        "stable-key",
        order_time,
    )
    order_two = store.create_order(
        first,
        "STOCK",
        "AAPL",
        "BUY",
        1.0,
        "ENTRY_SIGNAL",
        "stable-key",
        order_time,
    )

    assert first == second
    assert order_one == order_two
    portfolios = {item["kind"]: item for item in store.portfolios(first)}
    assert portfolios["STOCK"]["cash"] == 5_000
    assert portfolios["CRYPTO"]["cash"] == 5_000
    assert len(store.pending_orders(first)) == 1


def test_store_migrates_legacy_quote_and_signal_tables(tmp_path):
    path = tmp_path / "legacy.sqlite3"
    with sqlite3.connect(path) as db:
        db.executescript(
            """
            CREATE TABLE prices (
                id INTEGER PRIMARY KEY, drill_id INTEGER, portfolio TEXT,
                symbol TEXT, price REAL, source TEXT, source_timestamp TEXT,
                captured_at TEXT
            );
            CREATE TABLE signals (
                id INTEGER PRIMARY KEY, drill_id INTEGER, portfolio TEXT,
                symbol TEXT, signal TEXT, source TEXT, ml_probability REAL,
                ta_probability REAL, reason TEXT, decided_at TEXT
            );
            """
        )

    DrillStore(path)

    with sqlite3.connect(path) as db:
        price_columns = {row[1] for row in db.execute("PRAGMA table_info(prices)")}
        signal_columns = {row[1] for row in db.execute("PRAGMA table_info(signals)")}
    assert {"period_start", "period_end"} <= price_columns
    assert {
        "fused_probability",
        "confidence",
        "threshold_used",
        "policy_version",
        "confirmation_json",
    } <= signal_columns


def test_force_reset_is_refused_after_a_fill(tmp_path):
    store = DrillStore(tmp_path / "drill.sqlite3")
    config = DrillConfig(
        session_date=date(2026, 6, 12),
        stock_symbols=("AAPL",),
        crypto_symbols=(),
    )
    drill_id = store.create_drill(config)
    order_id = store.create_order(
        drill_id,
        "STOCK",
        "AAPL",
        "BUY",
        1.0,
        "ENTRY_SIGNAL",
        "force-reset-test",
        datetime.now(EASTERN),
    )
    with store.connection() as db:
        db.execute(
            """
            INSERT INTO fills(
                drill_id, order_id, portfolio, symbol, side, quantity,
                market_price, fill_price, fee, slippage, filled_at
            ) VALUES (?, ?, 'STOCK', 'AAPL', 'BUY', 1, 100, 100, 0, 0, ?)
            """,
            (drill_id, order_id, datetime.now(EASTERN).isoformat()),
        )

    try:
        store.reset_for_preparation(drill_id, config)
    except ValueError as exc:
        assert "already has fills" in str(exc)
    else:
        raise AssertionError("reset should be refused after a fill")
