from __future__ import annotations

from datetime import date

import pytest
from fastapi import HTTPException

from tradex.auto import api
from tradex.auto.engine import AutoTradingEngine
from tradex.auto.profiles import one_day_drill_profile
from tradex.drill.store import DrillStore


def test_auto_status_runs_and_halt_endpoints(tmp_path, monkeypatch):
    profile = one_day_drill_profile()
    store = DrillStore(tmp_path / "auto.sqlite3")
    run_id = store.create_drill(
        profile.to_drill_config(date(2026, 6, 12)),
        profile_name=profile.name,
        profile_version=profile.version,
        execution_mode=profile.execution_mode,
    )
    engine = AutoTradingEngine(profile=profile, store=store)
    monkeypatch.setattr("tradex.auto.api.default_engine", lambda: engine)

    status = api.auto_status()
    runs = api.auto_runs()
    with pytest.raises(HTTPException) as exc:
        api.auto_halt(api.HaltRequest(confirmation="NO"))
    halted = api.auto_halt(api.HaltRequest(confirmation="HALT"))

    assert status["drill"]["id"] == run_id
    assert runs["runs"][0]["id"] == run_id
    assert exc.value.status_code == 400
    assert halted["status"] == "HALTED"
    assert store.drill(run_id)["status"] == "HALTED"
