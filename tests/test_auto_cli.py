from __future__ import annotations

from click.testing import CliRunner

from tradex.__main__ import cli


def test_auto_profiles_cli_lists_one_day_drill():
    result = CliRunner().invoke(cli, ["auto", "profiles"])

    assert result.exit_code == 0
    assert "one-day-drill" in result.output
    assert "stocks-only-week-drill" in result.output
    assert "SIMULATED" in result.output


def test_auto_prepare_week_uses_stock_only_profile(tmp_path, monkeypatch):
    from tradex.drill.store import DrillStore

    store = DrillStore(tmp_path / "auto.sqlite3")

    def engine_for_profile(profile_name="one-day-drill"):
        from tradex.auto.engine import AutoTradingEngine
        from tradex.auto.profiles import get_profile

        engine = AutoTradingEngine(profile=get_profile(profile_name), store=store)
        engine.signals.prepare = lambda drill_id, config: None
        return engine

    monkeypatch.setattr("tradex.__main__._auto_engine", engine_for_profile)

    result = CliRunner().invoke(
        cli,
        [
            "auto",
            "prepare-week",
            "--start",
            "2026-06-17",
            "--end",
            "2026-06-19",
            "--exclude-date",
            "2026-06-19",
            "--force",
        ],
    )

    assert result.exit_code == 0
    runs = store.runs()
    assert len(runs) == 2
    assert {run["profile_name"] for run in runs} == {"stocks-only-week-drill"}
    for run in runs:
        assert run["config"]["crypto_symbols"] == []
        assert run["config"]["stock_symbols"] == ["SPY", "QQQ", "AAPL", "MSFT", "NVDA"]
