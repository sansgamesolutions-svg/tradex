from __future__ import annotations

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
