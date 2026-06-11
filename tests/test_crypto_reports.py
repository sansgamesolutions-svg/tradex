from tradex.crypto.types import (
    CryptoEligibilityResult,
    CryptoQualification,
    CryptoQualificationReport,
    CryptoThresholds,
)


def test_crypto_report_json_round_trip(tmp_path):
    report = CryptoQualificationReport(
        generated_at="2026-06-11T00:00:00+00:00",
        universe_name="Kraken USD Spot",
        universe_retrieved_at="2026-06-11T00:00:00+00:00",
        universe_source="kraken:test",
        exchange="kraken",
        model="xgboost",
        timeframe="1d",
        thresholds=CryptoThresholds(),
        results=(
            CryptoQualification(
                symbol="BTC/USD",
                approved=True,
                eligibility=CryptoEligibilityResult(
                    eligible=True,
                    reasons=(),
                    bars=720,
                    feature_samples=500,
                    median_quote_volume=50_000_000,
                    missing_day_rate=0,
                    stale_days=0,
                    minority_class_rate=0.49,
                    data_start="2024-01-01",
                    data_end="2026-01-01",
                ),
            ),
        ),
    )
    path = tmp_path / "crypto.json"

    report.write_json(path)

    assert CryptoQualificationReport.read_json(path) == report
