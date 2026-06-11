from __future__ import annotations

from dataclasses import replace

import numpy as np
import pandas as pd
import pytest

from tradex.models.base import BaseModel
from tradex.stocks.pipeline import (
    approve_folds,
    completed_daily_bars,
    evaluate_eligibility,
    evaluate_walk_forward,
    train_approved_stocks,
    walk_forward_splits,
)
from tradex.stocks.types import (
    EligibilityResult,
    FoldMetrics,
    QualificationReport,
    StockQualification,
    StockThresholds,
)


def make_stock_data(n=300, price=100.0, volume=1_000_000.0):
    index = pd.bdate_range("2020-01-01", periods=n, tz="UTC")
    close = price + np.sin(np.arange(n) / 5)
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


def permissive_thresholds():
    return StockThresholds(
        min_bars=20,
        min_feature_samples=10,
        min_price=5,
        min_median_dollar_volume=1_000,
        dollar_volume_window=10,
        max_missing_session_rate=0.01,
        max_stale_sessions=3,
        min_minority_class_rate=0.35,
        walk_forward_folds=4,
        walk_forward_initial_fraction=0.6,
        min_median_roc_auc=0.52,
        min_median_balanced_accuracy=0.51,
        min_folds_beating_baseline=3,
    )


def eligibility_for(raw, benchmark=None, target=None, thresholds=None):
    benchmark = benchmark if benchmark is not None else raw
    features = pd.DataFrame({"feature": range(len(raw))}, index=raw.index)
    if target is None:
        target = pd.Series(np.arange(len(raw)) % 2, index=raw.index)
    return evaluate_eligibility(
        raw,
        benchmark,
        features,
        target,
        thresholds or permissive_thresholds(),
    )


def test_eligibility_accepts_clean_liquid_history():
    result = eligibility_for(make_stock_data())

    assert result.eligible
    assert result.reasons == ()


def test_current_session_bar_is_removed_before_market_close():
    raw = make_stock_data(3)
    current_date = raw.index[-1].date()
    now = pd.Timestamp(current_date, tz="America/New_York") + pd.Timedelta(hours=12)

    completed = completed_daily_bars(raw, now=now.to_pydatetime())

    assert len(completed) == 2


@pytest.mark.parametrize(
    ("mutation", "reason"),
    [
        (lambda frame: frame.iloc[:10], "requires at least 20 daily bars"),
        (
            lambda frame: frame.assign(close=4.0),
            "latest close is below $5",
        ),
        (
            lambda frame: frame.assign(volume=1.0),
            "median daily dollar volume is below threshold",
        ),
    ],
)
def test_eligibility_rejects_basic_threshold_failures(mutation, reason):
    result = eligibility_for(mutation(make_stock_data()))

    assert not result.eligible
    assert reason in result.reasons


def test_eligibility_rejects_missing_and_stale_sessions():
    benchmark = make_stock_data()
    raw = benchmark.drop(benchmark.index[[10, 20]]).iloc[:-5]

    result = eligibility_for(raw, benchmark=benchmark)

    assert "missing-session rate exceeds threshold" in result.reasons
    assert "latest bar is stale" in result.reasons


def test_eligibility_rejects_duplicate_and_non_finite_bars():
    raw = make_stock_data()
    duplicate = pd.concat([raw, raw.iloc[[-1]]])
    duplicate.iloc[-1, duplicate.columns.get_loc("close")] = np.inf

    result = eligibility_for(duplicate, benchmark=raw)

    assert "duplicate bars" in result.reasons
    assert "non-finite OHLCV values" in result.reasons


def test_eligibility_rejects_imbalanced_target():
    raw = make_stock_data()
    target = pd.Series(1, index=raw.index)

    result = eligibility_for(raw, target=target)

    assert "target minority class is below threshold" in result.reasons


def test_walk_forward_splits_are_expanding_and_chronological():
    splits = list(walk_forward_splits(100, folds=4, initial_fraction=0.6))

    assert [(item[0].stop, item[1].start, item[1].stop) for item in splits] == [
        (60, 60, 70),
        (70, 70, 80),
        (80, 80, 90),
        (90, 90, 100),
    ]


class SignalModel(BaseModel):
    name = "signal"

    def fit(self, X, y):
        self.fitted_until = X.index[-1]

    def predict_probabilities(self, X):
        return X["signal"].to_numpy(dtype=float)

    def evaluate(self, X, y):
        return {}


def test_walk_forward_metrics_use_only_prior_training_data():
    index = pd.bdate_range("2020-01-01", periods=100, tz="UTC")
    target = pd.Series(np.arange(100) % 2, index=index)
    features = pd.DataFrame({"signal": target * 0.98 + 0.01}, index=index)

    folds = evaluate_walk_forward(
        features,
        target,
        "signal",
        permissive_thresholds(),
        lambda _: SignalModel(),
    )

    assert len(folds) == 4
    assert all(fold.train_end < fold.test_start for fold in folds)
    assert all(fold.roc_auc == 1.0 for fold in folds)
    assert all(fold.beats_baseline for fold in folds)


def fold(roc_auc=0.52, balanced=0.51, beats=True):
    return FoldMetrics(
        fold=1,
        train_start="2020-01-01",
        train_end="2021-01-01",
        test_start="2021-01-02",
        test_end="2021-06-01",
        train_samples=100,
        test_samples=20,
        roc_auc=roc_auc,
        balanced_accuracy=balanced,
        accuracy=0.55 if beats else 0.45,
        majority_baseline_accuracy=0.5,
        beats_baseline=beats,
    )


def test_approval_thresholds_are_inclusive():
    folds = tuple(replace(fold(), fold=i) for i in range(1, 5))

    approved, median_roc, median_balanced, beats, reasons = approve_folds(
        folds, permissive_thresholds()
    )

    assert approved
    assert median_roc == 0.52
    assert median_balanced == 0.51
    assert beats == 4
    assert reasons == ()


def test_approval_rejects_metrics_below_boundaries():
    folds = tuple(
        replace(fold(roc_auc=0.51, balanced=0.50, beats=i < 3), fold=i) for i in range(1, 5)
    )

    approved, _, _, beats, reasons = approve_folds(folds, permissive_thresholds())

    assert not approved
    assert beats == 2
    assert len(reasons) == 3


class SavingModel(BaseModel):
    name = "saving"

    def fit(self, X, y):
        self.was_fit = True

    def predict_probabilities(self, X):
        return np.full(len(X), 0.5)

    def evaluate(self, X, y):
        return {}

    def save(self, asset, timeframe):
        return f"saved/{asset}_{timeframe}.pkl"


def approved_result(symbol):
    eligibility = EligibilityResult(
        eligible=True,
        reasons=(),
        bars=300,
        feature_samples=100,
        latest_close=100,
        median_dollar_volume=100_000_000,
        missing_session_rate=0,
        stale_sessions=0,
        minority_class_rate=0.5,
        data_start="2020-01-01",
        data_end="2021-01-01",
    )
    return StockQualification(symbol=symbol, approved=True, eligibility=eligibility)


def test_batch_training_continues_after_symbol_failure():
    report = QualificationReport(
        generated_at="2026-06-11T00:00:00+00:00",
        universe_name="S&P 500",
        universe_retrieved_at="2026-06-11T00:00:00+00:00",
        universe_source_url="https://example.test",
        model="saving",
        timeframe="1d",
        training_start="2020-01-01",
        thresholds=permissive_thresholds(),
        results=(approved_result("GOOD"), approved_result("BAD")),
    )

    def fetcher(symbol, timeframe, start=None, force_refresh=False):
        if symbol == "BAD":
            raise ValueError("download failed")
        return make_stock_data()

    outcomes = train_approved_stocks(
        report,
        data_fetcher=fetcher,
        model_factory=lambda _: SavingModel(),
    )

    assert outcomes["GOOD"] == "saved/GOOD_1d.pkl"
    assert outcomes["BAD"] == "ERROR: download failed"
