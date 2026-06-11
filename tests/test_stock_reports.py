import csv

from tradex.stocks.types import (
    EligibilityResult,
    QualificationReport,
    StockQualification,
    StockThresholds,
)


def test_report_json_and_csv_round_trip(tmp_path):
    eligibility = EligibilityResult(
        eligible=True,
        reasons=(),
        bars=1250,
        feature_samples=1000,
        latest_close=100,
        median_dollar_volume=50_000_000,
        missing_session_rate=0,
        stale_sessions=0,
        minority_class_rate=0.49,
        data_start="2020-01-01T00:00:00+00:00",
        data_end="2026-01-01T00:00:00+00:00",
    )
    report = QualificationReport(
        generated_at="2026-06-11T00:00:00+00:00",
        universe_name="S&P 500",
        universe_retrieved_at="2026-06-10T00:00:00+00:00",
        universe_source_url="https://example.test",
        model="xgboost",
        timeframe="1d",
        training_start="2016-01-01",
        thresholds=StockThresholds(),
        results=(
            StockQualification(
                symbol="AAPL",
                approved=True,
                eligibility=eligibility,
                median_roc_auc=0.55,
                median_balanced_accuracy=0.53,
                folds_beating_baseline=4,
            ),
        ),
    )
    json_path = tmp_path / "report.json"
    csv_path = tmp_path / "report.csv"

    report.write_json(json_path)
    report.write_csv(csv_path)

    assert QualificationReport.read_json(json_path) == report
    with csv_path.open(newline="", encoding="utf-8") as file:
        rows = list(csv.DictReader(file))
    assert rows[0]["symbol"] == "AAPL"
    assert rows[0]["approved"] == "True"
