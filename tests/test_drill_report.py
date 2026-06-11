from __future__ import annotations

from datetime import date

from tradex.drill.report import build_report, write_report
from tradex.drill.store import DrillStore
from tradex.drill.types import DrillConfig


def test_report_contains_two_books_benchmarks_and_recommendations(tmp_path):
    store = DrillStore(tmp_path / "drill.sqlite3")
    drill_id = store.create_drill(DrillConfig(session_date=date(2026, 6, 12)))
    store.set_status(drill_id, "COMPLETED")

    report = build_report(store, drill_id)
    json_path = write_report(report, tmp_path / "report.json", "json")
    html_path = write_report(report, tmp_path / "report.html", "html")

    assert {item["kind"] for item in report.portfolios} == {"STOCK", "CRYPTO"}
    assert report.combined["benchmark_5_percent"] == 10_500
    assert report.recommendations
    assert json_path.read_text(encoding="utf-8").startswith("{")
    assert "TradeX Drill Report" in html_path.read_text(encoding="utf-8")
