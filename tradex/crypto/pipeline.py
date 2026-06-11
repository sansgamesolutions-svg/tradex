from __future__ import annotations

from collections.abc import Callable
from datetime import UTC, datetime

import numpy as np
import pandas as pd

from tradex.crypto.data import KrakenMarketData
from tradex.crypto.types import (
    CryptoEligibilityResult,
    CryptoQualification,
    CryptoQualificationReport,
    CryptoThresholds,
)
from tradex.crypto.universe import CryptoUniverse
from tradex.models import BaseModel, get_model
from tradex.stocks.pipeline import (
    aligned_training_data,
    approve_folds,
    evaluate_walk_forward,
)

ModelFactory = Callable[[str], BaseModel]


def evaluate_crypto_eligibility(
    raw_df: pd.DataFrame,
    features: pd.DataFrame,
    target: pd.Series,
    thresholds: CryptoThresholds,
    *,
    today: datetime | None = None,
) -> CryptoEligibilityResult:
    reasons: list[str] = []
    numeric = raw_df[["open", "high", "low", "close", "volume"]]
    if raw_df.index.duplicated().any():
        reasons.append("duplicate bars")
    if not np.isfinite(numeric.to_numpy(dtype=float)).all():
        reasons.append("non-finite OHLCV values")

    bars = len(raw_df)
    if bars < thresholds.min_bars:
        reasons.append(f"requires at least {thresholds.min_bars} daily bars")
    feature_samples = len(features)
    if feature_samples < thresholds.min_feature_samples:
        reasons.append(f"requires at least {thresholds.min_feature_samples} feature samples")

    quote_volume = (raw_df["close"] * raw_df["volume"]).tail(thresholds.quote_volume_window)
    median_quote_volume = float(quote_volume.median()) if not quote_volume.empty else 0.0
    if not np.isfinite(median_quote_volume):
        median_quote_volume = 0.0
    if median_quote_volume < thresholds.min_median_quote_volume:
        reasons.append("median daily USD volume is below threshold")

    if bars:
        expected = pd.date_range(
            raw_df.index[0].normalize(),
            raw_df.index[-1].normalize(),
            freq="D",
            tz="UTC",
        )
        missing_day_rate = 1.0 - len(raw_df.index.normalize().unique()) / len(expected)
        current_date = (today or datetime.now(UTC)).date()
        stale_days = max((current_date - raw_df.index[-1].date()).days - 1, 0)
    else:
        missing_day_rate = 1.0
        stale_days = thresholds.max_stale_days + 1
    if missing_day_rate > thresholds.max_missing_day_rate:
        reasons.append("missing-day rate exceeds threshold")
    if stale_days > thresholds.max_stale_days:
        reasons.append("latest bar is stale")

    minority_class_rate = (
        float(target.value_counts(normalize=True).min()) if target.nunique() == 2 else 0.0
    )
    if minority_class_rate < thresholds.min_minority_class_rate:
        reasons.append("target minority class is below threshold")

    return CryptoEligibilityResult(
        eligible=not reasons,
        reasons=tuple(reasons),
        bars=bars,
        feature_samples=feature_samples,
        median_quote_volume=median_quote_volume,
        missing_day_rate=float(missing_day_rate),
        stale_days=stale_days,
        minority_class_rate=minority_class_rate,
        data_start=raw_df.index[0].isoformat() if bars else "",
        data_end=raw_df.index[-1].isoformat() if bars else "",
    )


class CryptoQualificationPipeline:
    def __init__(
        self,
        *,
        thresholds: CryptoThresholds | None = None,
        market_data: KrakenMarketData | None = None,
        model_factory: ModelFactory = get_model,
    ) -> None:
        self.thresholds = thresholds or CryptoThresholds.from_settings()
        self.market_data = market_data or KrakenMarketData()
        self.model_factory = model_factory

    def qualify(
        self,
        universe: CryptoUniverse,
        *,
        model_name: str = "xgboost",
    ) -> CryptoQualificationReport:
        run_time = datetime.now(UTC)
        try:
            results = tuple(
                self._qualify_symbol(market.symbol, model_name, run_time)
                for market in universe.markets
            )
        finally:
            self.market_data.close()
        return CryptoQualificationReport(
            generated_at=datetime.now(UTC).isoformat(),
            universe_name=universe.name,
            universe_retrieved_at=universe.retrieved_at,
            universe_source=universe.source,
            exchange=universe.exchange,
            model=model_name,
            timeframe="1d",
            thresholds=self.thresholds,
            results=results,
        )

    def _qualify_symbol(
        self,
        symbol: str,
        model_name: str,
        run_time: datetime,
    ) -> CryptoQualification:
        try:
            raw_df = self.market_data.fetch_daily(symbol, now=run_time)
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
            eligibility = evaluate_crypto_eligibility(
                raw_df,
                features,
                target,
                self.thresholds,
                today=run_time,
            )
            if not eligibility.eligible:
                return CryptoQualification(
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
            return CryptoQualification(
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
            return CryptoQualification(
                symbol=symbol,
                approved=False,
                rejection_reasons=("qualification failed",),
                error=str(exc),
            )


def train_approved_crypto(
    report: CryptoQualificationReport,
    *,
    market_data: KrakenMarketData | None = None,
    model_factory: ModelFactory = get_model,
) -> dict[str, str]:
    data = market_data or KrakenMarketData()
    outcomes: dict[str, str] = {}
    try:
        for symbol in report.approved_symbols:
            try:
                raw_df = data.fetch_daily(symbol)
                features, target = aligned_training_data(raw_df)
                model = model_factory(report.model)
                model.fit(features, target)
                outcomes[symbol] = model.save(symbol, report.timeframe)
            except Exception as exc:
                outcomes[symbol] = f"ERROR: {exc}"
    finally:
        data.close()
    return outcomes
