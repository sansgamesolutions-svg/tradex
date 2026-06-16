from __future__ import annotations

from datetime import UTC, date, datetime

import pytest

from tradex.auto.engine import AutoTradingEngine
from tradex.auto.profiles import one_day_drill_profile
from tradex.auto.types import TradingProfile
from tradex.drill.store import DrillStore
from tradex.execution.models import OrderRequest


def test_unsupported_execution_mode_fails_closed(tmp_path):
    profile = TradingProfile(
        **{
            **one_day_drill_profile().__dict__,
            "execution_mode": "BROKER_LIVE",
        }
    )
    engine = AutoTradingEngine(profile=profile, store=DrillStore(tmp_path / "auto.sqlite3"))

    with pytest.raises(ValueError, match="disabled in v1"):
        engine.prepare(date(2026, 6, 12))

    drill_id = engine.store.latest_drill_id()
    assert drill_id is not None
    assert engine.store.drill(drill_id)["status"] == "FAILED"
    assert any(
        event["category"] == "EXECUTION" and event["level"] == "ERROR"
        for event in engine.store.table("events", drill_id)
    )


def test_broker_router_rejects_non_simulated_mode_without_live_adapter(tmp_path):
    profile = TradingProfile(
        **{
            **one_day_drill_profile().__dict__,
            "execution_mode": "BROKER_PAPER",
        }
    )
    engine = AutoTradingEngine(profile=profile, store=DrillStore(tmp_path / "auto.sqlite3"))

    with pytest.raises(RuntimeError, match="disabled in v1"):
        engine.assert_route_supported(
            OrderRequest(symbol="AAPL", side="BUY", quantity=1, asset_type="STOCK")
        )


def test_past_unstarted_session_completes_no_run(tmp_path):
    profile = one_day_drill_profile()
    store = DrillStore(tmp_path / "auto.sqlite3")
    config = profile.to_drill_config(date(2026, 6, 12))
    drill_id = store.create_drill(
        config,
        profile_name=profile.name,
        profile_version=profile.version,
        execution_mode=profile.execution_mode,
    )
    store.set_status(drill_id, "PREPARED")
    engine = AutoTradingEngine(
        profile=profile,
        store=store,
        clock=lambda: datetime(2026, 6, 16, 12, 0, tzinfo=UTC),
    )

    engine.run_cycle(drill_id)

    drill = store.drill(drill_id)
    assert drill["status"] == "COMPLETED_NO_RUN"
    assert "session ended" in drill["expired_reason"]
    assert store.table("orders", drill_id) == []


def test_status_exposes_profile_execution_and_scheduler_health(tmp_path):
    profile = one_day_drill_profile()
    store = DrillStore(tmp_path / "auto.sqlite3")
    drill_id = store.create_drill(
        profile.to_drill_config(date(2026, 6, 12)),
        profile_name=profile.name,
        profile_version=profile.version,
        execution_mode=profile.execution_mode,
    )
    engine = AutoTradingEngine(profile=profile, store=store)

    status = engine.status(drill_id)

    assert status["profile"]["name"] == "one-day-drill"
    assert status["profile"]["execution_mode"] == "SIMULATED"
    assert status["automation"]["broker_execution_enabled"] is False
    assert "scheduler_health" in status
