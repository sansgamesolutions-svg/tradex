from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from tradex.drill import dashboard
from tradex.drill.engine import DrillEngine
from tradex.drill.store import DrillStore
from tradex.drill.types import DrillConfig


def test_dashboard_status_and_confirmed_halt(tmp_path, monkeypatch):
    store = DrillStore(tmp_path / "drill.sqlite3")
    drill_id = store.create_drill(DrillConfig(session_date=date(2026, 6, 12)))
    engine = DrillEngine(store=store)
    monkeypatch.setattr("tradex.drill.dashboard.default_engine", lambda: engine)

    page = dashboard.drill_dashboard()
    status = dashboard.drill_status()
    with pytest.raises(HTTPException) as rejected:
        dashboard.halt_drill(dashboard.HaltRequest(confirmation="no"))
    halted = dashboard.halt_drill(dashboard.HaltRequest(confirmation="HALT"))

    assert "TradeX One-Day Paper Drill" in page
    assert status["drill"]["id"] == drill_id
    assert rejected.value.status_code == 400
    assert halted["status"] == "HALTED"
    assert store.drill(drill_id)["status"] == "HALTED"
