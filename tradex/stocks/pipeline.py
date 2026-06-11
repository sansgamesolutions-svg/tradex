from __future__ import annotations

from collections.abc import Callable, Iterator
from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo

import numpy as np
import pandas as pd
from sklearn.metrics import accuracy_score, balanced_accuracy_score, roc_auc_score

from tradex.data.fetcher import fetch
from tradex.data.preprocessor import build_features, make_target
from tradex.indicators.technical import add_indicators
from tradex.models import BaseModel, get_model
from tradex.stocks.types import (
    EligibilityResult,
    FoldMetrics,
    QualificationReport,
    StockQualification,
    StockThresholds,
)
from tradex.stocks.universe import StockUniverse

DataFetcher = Callable[..., pd.DataFrame]
ModelFactory = Callable[[str], BaseModel]


def completed_daily_bars(
    raw_df: pd.DataFrame,
    *,
    now: datetime | None = None,
) -> pd.DataFrame:
    if raw_df.empty:
        return raw_df
    current = (now or datetime.now(UTC)).astimezone(ZoneInfo("America/New_York"))
    completed = raw_df[raw_df.index.date <= current.date()]
    if current.time() < time(16, 15):
        completed = completed[completed.index.date < current.date()]
    return completed


def aligned_training_data(raw_df: pd.DataFrame) -> tuple[pd.DataFrame, pd.Series]:
    enriched = add_indicators(raw_df)
    features = build_features(enriched)
    target = make_target(enriched)
    index = features.index.intersection(target.index)
    return features.loc[index], target.loc[index]


def walk_forward_splits(
    samples: int,
    *,
    folds: int,
    initial_fraction: float,
) -> Iterator[tuple[slice, slice]]:
    if folds < 1:
        raise ValueError("folds must be at least 1")
    initial_end = int(samples * initial_fraction)
    remaining = samples - initial_end
    test_size = remaining // folds
    if initial_end < 1 or test_size < 1:
        raise ValueError("not enough samples for walk-forward validation")

    for fold in range(folds):
        train_end = initial_end + fold * test_size
        test_end = samples if fold == folds - 1 else train_end + test_size
        yield slice(0, train_end), slice(train_end, test_end)


def evaluate_eligibility(
    raw_df: pd.DataFrame,
    benchmark_df: pd.DataFrame,
    features: pd.DataFrame,
    target: pd.Series,
    thresholds: StockThresholds,
) -> EligibilityResult:
    reasons: list[str] = []
    numeric = raw_df[["open", "high", "low", "close", "volume"]]
    has_duplicates = raw_df.index.duplicated().any()
    has_non_finite = not np.isfinite(numeric.to_numpy(dtype=float)).all()
    if has_duplicates:
        reasons.append("duplicate bars")
    if has_non_finite:
        reasons.append("non-finite OHLCV values")

    bars = len(raw_df)
    if bars < thresholds.min_bars:
        reasons.append(f"requires at least {thresholds.min_bars} daily bars")

    feature_samples = len(features)
    if feature_samples < thresholds.min_feature_samples:
        reasons.append(f"requires at least {thresholds.min_feature_samples} feature samples")

    latest_close = float(raw_df["close"].iloc[-1]) if bars else 0.0
    if not np.isfinite(latest_close):
        latest_close = 0.0
    if latest_close < thresholds.min_price:
        reasons.append(f"latest close is below ${thresholds.min_price:g}")

    dollar_volume = (raw_df["close"] * raw_df["volume"]).tail(thresholds.dollar_volume_window)
    median_dollar_volume = float(dollar_volume.median()) if not dollar_volume.empty else 0.0
    if not np.isfinite(median_dollar_volume):
        median_dollar_volume = 0.0
    if median_dollar_volume < thresholds.min_median_dollar_volume:
        reasons.append("median daily dollar volume is below threshold")

    if bars:
        expected = benchmark_df.index[
            (benchmark_df.index >= raw_df.index[0]) & (benchmark_df.index <= benchmark_df.index[-1])
        ]
        observed = raw_df.index.intersection(expected)
        missing_session_rate = 1.0 - len(observed) / len(expected) if len(expected) else 1.0
        stale_sessions = int((benchmark_df.index > raw_df.index[-1]).sum())
    else:
        missing_session_rate = 1.0
        stale_sessions = len(benchmark_df)

    if missing_session_rate > thresholds.max_missing_session_rate:
        reasons.append("missing-session rate exceeds threshold")
    if stale_sessions > thresholds.max_stale_sessions:
        reasons.append("latest bar is stale")

    minority_class_rate = (
        float(target.value_counts(normalize=True).min()) if target.nunique() == 2 else 0.0
    )
    if minority_class_rate < thresholds.min_minority_class_rate:
        reasons.append("target minority class is below threshold")

    return EligibilityResult(
        eligible=not reasons,
        reasons=tuple(reasons),
        bars=bars,
        feature_samples=feature_samples,
        latest_close=latest_close,
        median_dollar_volume=median_dollar_volume,
        missing_session_rate=float(missing_session_rate),
        stale_sessions=stale_sessions,
        minority_class_rate=minority_class_rate,
        data_start=raw_df.index[0].isoformat() if bars else "",
        data_end=raw_df.index[-1].isoformat() if bars else "",
    )


def _aligned_probabilities(
    model: BaseModel,
    X_test: pd.DataFrame,
    y_test: pd.Series,
) -> tuple[np.ndarray, np.ndarray]:
    probabilities = np.asarray(model.predict_probabilities(X_test), dtype=float)
    if len(probabilities) == 0:
        raise ValueError("model returned no predictions for the test fold")
    if len(probabilities) > len(y_test):
        raise ValueError("model returned more predictions than test samples")
    targets = y_test.iloc[-len(probabilities) :].to_numpy(dtype=int)
    return probabilities, targets


def evaluate_walk_forward(
    features: pd.DataFrame,
    target: pd.Series,
    model_name: str,
    thresholds: StockThresholds,
    model_factory: ModelFactory,
) -> tuple[FoldMetrics, ...]:
    folds: list[FoldMetrics] = []
    for fold_number, (train_slice, test_slice) in enumerate(
        walk_forward_splits(
            len(features),
            folds=thresholds.walk_forward_folds,
            initial_fraction=thresholds.walk_forward_initial_fraction,
        ),
        start=1,
    ):
        X_train, X_test = features.iloc[train_slice], features.iloc[test_slice]
        y_train, y_test = target.iloc[train_slice], target.iloc[test_slice]
        model = model_factory(model_name)
        model.fit(X_train, y_train)
        probabilities, targets = _aligned_probabilities(model, X_test, y_test)
        predictions = (probabilities >= 0.5).astype(int)
        prediction_index = y_test.index[-len(targets) :]
        majority_class = int(y_train.mean() >= 0.5)
        baseline = np.full(len(targets), majority_class, dtype=int)
        accuracy = float(accuracy_score(targets, predictions))
        baseline_accuracy = float(accuracy_score(targets, baseline))
        try:
            roc_auc = float(roc_auc_score(targets, probabilities))
        except ValueError:
            roc_auc = 0.5

        folds.append(
            FoldMetrics(
                fold=fold_number,
                train_start=X_train.index[0].isoformat(),
                train_end=X_train.index[-1].isoformat(),
                test_start=prediction_index[0].isoformat(),
                test_end=prediction_index[-1].isoformat(),
                train_samples=len(X_train),
                test_samples=len(targets),
                roc_auc=roc_auc,
                balanced_accuracy=float(balanced_accuracy_score(targets, predictions)),
                accuracy=accuracy,
                majority_baseline_accuracy=baseline_accuracy,
                beats_baseline=accuracy > baseline_accuracy,
            )
        )
    return tuple(folds)


def approve_folds(
    folds: tuple[FoldMetrics, ...],
    thresholds: StockThresholds,
) -> tuple[bool, float, float, int, tuple[str, ...]]:
    median_roc_auc = float(np.median([fold.roc_auc for fold in folds]))
    median_balanced_accuracy = float(np.median([fold.balanced_accuracy for fold in folds]))
    beats = sum(fold.beats_baseline for fold in folds)
    reasons: list[str] = []
    if median_roc_auc < thresholds.min_median_roc_auc:
        reasons.append("median ROC-AUC is below threshold")
    if median_balanced_accuracy < thresholds.min_median_balanced_accuracy:
        reasons.append("median balanced accuracy is below threshold")
    if beats < thresholds.min_folds_beating_baseline:
        reasons.append("too few folds beat the majority baseline")
    return (
        not reasons,
        median_roc_auc,
        median_balanced_accuracy,
        beats,
        tuple(reasons),
    )


class StockQualificationPipeline:
    def __init__(
        self,
        *,
        thresholds: StockThresholds | None = None,
        data_fetcher: DataFetcher = fetch,
        model_factory: ModelFactory = get_model,
    ) -> None:
        self.thresholds = thresholds or StockThresholds.from_settings()
        self.data_fetcher = data_fetcher
        self.model_factory = model_factory

    def qualify(
        self,
        universe: StockUniverse,
        *,
        model_name: str = "xgboost",
        training_start: str | None = None,
    ) -> QualificationReport:
        start = training_start or (datetime.now(UTC).date() - timedelta(days=365 * 10)).isoformat()
        run_time = datetime.now(UTC)
        benchmark = completed_daily_bars(
            self.data_fetcher(
                "SPY",
                "1d",
                start=start,
                force_refresh=True,
            ),
            now=run_time,
        )
        results = tuple(
            self._qualify_symbol(
                item.yahoo_symbol,
                benchmark,
                model_name,
                start,
                run_time,
            )
            for item in universe.constituents
        )
        return QualificationReport(
            generated_at=datetime.now(UTC).isoformat(),
            universe_name=universe.name,
            universe_retrieved_at=universe.retrieved_at,
            universe_source_url=universe.source_url,
            model=model_name,
            timeframe="1d",
            training_start=start,
            thresholds=self.thresholds,
            results=results,
        )

    def _qualify_symbol(
        self,
        symbol: str,
        benchmark: pd.DataFrame,
        model_name: str,
        start: str,
        run_time: datetime,
    ) -> StockQualification:
        try:
            raw_df = completed_daily_bars(
                self.data_fetcher(
                    symbol,
                    "1d",
                    start=start,
                    force_refresh=True,
                ),
                now=run_time,
            )
            numeric = raw_df[["open", "high", "low", "close", "volume"]]
            structurally_invalid = (
                raw_df.index.duplicated().any()
                or not np.isfinite(numeric.to_numpy(dtype=float)).all()
            )
            if structurally_invalid:
                features = pd.DataFrame(index=raw_df.index[:0])
                target = pd.Series(dtype=int)
            else:
                features, target = aligned_training_data(raw_df)
            eligibility = evaluate_eligibility(raw_df, benchmark, features, target, self.thresholds)
            if not eligibility.eligible:
                return StockQualification(
                    symbol=symbol,
                    approved=False,
                    eligibility=eligibility,
                    rejection_reasons=eligibility.reasons,
                )

            folds = evaluate_walk_forward(
                features,
                target,
                model_name,
                self.thresholds,
                self.model_factory,
            )
            approved, median_roc_auc, median_balanced_accuracy, beats, reasons = approve_folds(
                folds, self.thresholds
            )

            return StockQualification(
                symbol=symbol,
                approved=approved,
                eligibility=eligibility,
                folds=folds,
                median_roc_auc=median_roc_auc,
                median_balanced_accuracy=median_balanced_accuracy,
                folds_beating_baseline=beats,
                rejection_reasons=reasons,
            )
        except Exception as exc:
            return StockQualification(
                symbol=symbol,
                approved=False,
                rejection_reasons=("qualification failed",),
                error=str(exc),
            )


def train_approved_stocks(
    report: QualificationReport,
    *,
    data_fetcher: DataFetcher = fetch,
    model_factory: ModelFactory = get_model,
) -> dict[str, str]:
    outcomes: dict[str, str] = {}
    for symbol in report.approved_symbols:
        try:
            raw_df = data_fetcher(
                symbol,
                report.timeframe,
                start=report.training_start,
                force_refresh=True,
            )
            features, target = aligned_training_data(raw_df)
            model = model_factory(report.model)
            model.fit(features, target)
            outcomes[symbol] = model.save(symbol, report.timeframe)
        except Exception as exc:
            outcomes[symbol] = f"ERROR: {exc}"
    return outcomes
