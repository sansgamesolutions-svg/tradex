from __future__ import annotations

import numpy as np
import pandas as pd

from tradex.crypto.pipeline import (
    evaluate_crypto_eligibility,
    train_approved_crypto,
)
from tradex.crypto.types import (
    CryptoEligibilityResult,
    CryptoQualification,
    CryptoQualificationReport,
    CryptoThresholds,
)
from tradex.models.base import BaseModel


def make_crypto_data(n=720, volume=100_000.0):
    index = pd.date_range("2024-06-21", periods=n, freq="D", tz="UTC")
    close = 100 + np.sin(np.arange(n) / 5)
    return pd.DataFrame(
        {
            "open": close - 0.2,
            "high": close + 1,
            "low": close - 1,
            "close": close,
            "volume": volume,
        },
        index=index,
    )


def thresholds():
    return CryptoThresholds(
        min_bars=20,
        min_feature_samples=10,
        min_median_quote_volume=1_000,
        quote_volume_window=10,
        max_missing_day_rate=0.01,
        max_stale_days=2,
        min_minority_class_rate=0.35,
        walk_forward_folds=4,
        walk_forward_initial_fraction=0.6,
        min_median_roc_auc=0.52,
        min_median_balanced_accuracy=0.51,
        min_folds_beating_baseline=3,
    )


def eligibility(raw, target=None):
    features = pd.DataFrame({"feature": range(len(raw))}, index=raw.index)
    target = target if target is not None else pd.Series(np.arange(len(raw)) % 2, index=raw.index)
    return evaluate_crypto_eligibility(
        raw,
        features,
        target,
        thresholds(),
        today=pd.Timestamp(raw.index[-1].date() + pd.Timedelta(days=1)).to_pydatetime(),
    )


def test_crypto_eligibility_accepts_continuous_liquid_data():
    result = eligibility(make_crypto_data())

    assert result.eligible
    assert result.reasons == ()


def test_crypto_eligibility_rejects_low_volume_missing_days_and_imbalance():
    raw = make_crypto_data(volume=1)
    raw = raw.drop(index=raw.index[10:20])
    target = pd.Series(1, index=raw.index)

    result = eligibility(raw, target)

    assert "median daily USD volume is below threshold" in result.reasons
    assert "missing-day rate exceeds threshold" in result.reasons
    assert "target minority class is below threshold" in result.reasons


def test_crypto_eligibility_rejects_stale_history():
    raw = make_crypto_data()
    features = pd.DataFrame({"feature": range(len(raw))}, index=raw.index)
    target = pd.Series(np.arange(len(raw)) % 2, index=raw.index)

    result = evaluate_crypto_eligibility(
        raw,
        features,
        target,
        thresholds(),
        today=pd.Timestamp(raw.index[-1].date() + pd.Timedelta(days=5)).to_pydatetime(),
    )

    assert "latest bar is stale" in result.reasons


class SavingModel(BaseModel):
    name = "saving"

    def fit(self, X, y):
        pass

    def predict_probabilities(self, X):
        return np.full(len(X), 0.5)

    def evaluate(self, X, y):
        return {}

    def save(self, asset, timeframe):
        return f"saved/{asset.replace('/', '_')}_{timeframe}.pkl"


class FakeMarketData:
    def __init__(self):
        self.closed = False

    def fetch_daily(self, symbol, **kwargs):
        if symbol == "BAD/USD":
            raise ValueError("download failed")
        return make_crypto_data()

    def close(self):
        self.closed = True


def approved(symbol):
    return CryptoQualification(
        symbol=symbol,
        approved=True,
        eligibility=CryptoEligibilityResult(
            eligible=True,
            reasons=(),
            bars=720,
            feature_samples=500,
            median_quote_volume=10_000_000,
            missing_day_rate=0,
            stale_days=0,
            minority_class_rate=0.5,
            data_start="2024-01-01",
            data_end="2026-01-01",
        ),
    )


def test_crypto_batch_training_continues_after_failure():
    report = CryptoQualificationReport(
        generated_at="2026-06-11T00:00:00+00:00",
        universe_name="Kraken USD Spot",
        universe_retrieved_at="2026-06-11T00:00:00+00:00",
        universe_source="kraken:test",
        exchange="kraken",
        model="saving",
        timeframe="1d",
        thresholds=thresholds(),
        results=(approved("BTC/USD"), approved("BAD/USD")),
    )
    data = FakeMarketData()

    outcomes = train_approved_crypto(
        report,
        market_data=data,
        model_factory=lambda _: SavingModel(),
    )

    assert outcomes["BTC/USD"] == "saved/BTC_USD_1d.pkl"
    assert outcomes["BAD/USD"] == "ERROR: download failed"
    assert data.closed
