from __future__ import annotations

import io
from collections.abc import Callable
from datetime import UTC, date, datetime

import joblib
import pandas as pd

from tradex.config.settings import settings
from tradex.crypto.pipeline import evaluate_crypto_eligibility
from tradex.crypto.types import CryptoThresholds
from tradex.data.preprocessor import build_features
from tradex.drill.market import DrillMarketData
from tradex.drill.store import DrillStore
from tradex.drill.types import DrillConfig, PortfolioKind, SignalDecision
from tradex.indicators.technical import add_indicators, ta_signal
from tradex.models import BaseModel, get_model
from tradex.stocks.pipeline import (
    aligned_training_data,
    approve_folds,
    evaluate_eligibility,
    evaluate_walk_forward,
)
from tradex.stocks.types import StockThresholds

ModelFactory = Callable[[str], BaseModel]


def completed_before(raw: pd.DataFrame, session_date: date) -> pd.DataFrame:
    """Defensively exclude the drill date and any future bars."""
    return raw[raw.index.date < session_date]


class DrillSignalService:
    """Prepare isolated models and make timestamped drill decisions."""

    def __init__(
        self,
        store: DrillStore,
        market_data: DrillMarketData,
        *,
        model_factory: ModelFactory = get_model,
    ) -> None:
        self.store = store
        self.market_data = market_data
        self.model_factory = model_factory

    def prepare(self, drill_id: int, config: DrillConfig) -> None:
        benchmark = self.market_data.fetch_daily("STOCK", "SPY", config.session_date)
        for portfolio, symbols in (
            ("STOCK", config.stock_symbols),
            ("CRYPTO", config.crypto_symbols),
        ):
            for symbol in symbols:
                self._prepare_symbol(drill_id, config, portfolio, symbol, benchmark)

    def _prepare_symbol(
        self,
        drill_id: int,
        config: DrillConfig,
        portfolio: PortfolioKind,
        symbol: str,
        benchmark: pd.DataFrame,
    ) -> None:
        try:
            raw = completed_before(
                self.market_data.fetch_daily(portfolio, symbol, config.session_date),
                config.session_date,
            )
            features, target = aligned_training_data(raw)
            thresholds = (
                StockThresholds.from_settings()
                if portfolio == "STOCK"
                else CryptoThresholds.from_settings()
            )
            if portfolio == "STOCK":
                eligibility = evaluate_eligibility(
                    raw,
                    benchmark,
                    features,
                    target,
                    thresholds,
                )
            else:
                eligibility = evaluate_crypto_eligibility(
                    raw,
                    features,
                    target,
                    thresholds,
                    today=datetime.combine(
                        config.session_date,
                        datetime.min.time(),
                        tzinfo=UTC,
                    ),
                )
            if not eligibility.eligible:
                self.store.record_preparation(
                    drill_id,
                    portfolio,
                    symbol,
                    approved=False,
                    source="TA_ONLY",
                    metrics={"eligibility": eligibility.__dict__},
                    reason="; ".join(eligibility.reasons),
                )
                return

            folds = evaluate_walk_forward(
                features,
                target,
                config.model_name,
                thresholds,
                self.model_factory,
            )
            approved, roc_auc, balanced_accuracy, beats, reasons = approve_folds(
                folds,
                thresholds,
            )
            metrics = {
                "median_roc_auc": roc_auc,
                "median_balanced_accuracy": balanced_accuracy,
                "folds_beating_baseline": beats,
                "folds": [fold.__dict__ for fold in folds],
            }
            artifact_path = None
            source = "TA_ONLY"
            if approved:
                model = self.model_factory(config.model_name)
                model.fit(features, target)
                artifact_path = self._save_model(drill_id, portfolio, symbol, model)
                source = "ML_TA"
            self.store.record_preparation(
                drill_id,
                portfolio,
                symbol,
                approved=approved,
                source=source,
                artifact_path=artifact_path,
                metrics=metrics,
                reason="; ".join(reasons) if reasons else "approved",
            )
        except Exception as exc:
            self.store.record_preparation(
                drill_id,
                portfolio,
                symbol,
                approved=False,
                source="TA_ONLY",
                metrics={},
                reason=f"preparation failed: {exc}",
            )
            self.store.record_event(
                drill_id,
                "SIGNAL",
                f"{portfolio} {symbol} model preparation failed",
                level="WARNING",
                details={"error": str(exc)},
            )

    def _save_model(
        self,
        drill_id: int,
        portfolio: PortfolioKind,
        symbol: str,
        model: BaseModel,
    ) -> str:
        from tradex.storage import get_storage

        key = f"drill/artifacts/{drill_id}/{portfolio.lower()}_{symbol.replace('/', '_')}_1d.pkl"
        buffer = io.BytesIO()
        joblib.dump(model, buffer)
        get_storage().put(key, buffer.getvalue())
        return key

    def decide(
        self,
        drill_id: int,
        config: DrillConfig,
        portfolio: PortfolioKind,
        symbol: str,
        decided_at: datetime,
    ) -> SignalDecision:
        raw = completed_before(
            self.market_data.fetch_daily(portfolio, symbol, config.session_date),
            config.session_date,
        )
        enriched = add_indicators(raw)
        features = build_features(enriched)
        score = float(ta_signal(enriched))
        ta_probability = (score + 1.0) / 2.0
        preparation = self.store.preparation(drill_id, portfolio, symbol)
        ml_probability: float | None = None
        source = "TA_ONLY"
        fused = ta_probability

        if preparation and preparation["approved"] and preparation["artifact_path"]:
            try:
                from tradex.storage import get_storage

                data = get_storage().get(preparation["artifact_path"])
                model = joblib.load(io.BytesIO(data))
                ml_probability = float(model.predict_proba(features))
                fused = settings.model_weight * ml_probability + settings.ta_weight * ta_probability
                source = "ML_TA"
            except Exception as exc:
                self.store.record_event(
                    drill_id,
                    "SIGNAL",
                    f"{portfolio} {symbol} model load failed; using TA only",
                    level="WARNING",
                    details={"error": str(exc)},
                    occurred_at=decided_at,
                )

        if fused >= settings.signal_threshold:
            signal = "BUY"
        elif fused <= 1.0 - settings.signal_threshold:
            signal = "SELL"
        else:
            signal = "HOLD"
        return SignalDecision(
            symbol=symbol,
            portfolio=portfolio,
            signal=signal,
            source=source,
            decided_at=decided_at,
            ml_probability=ml_probability,
            ta_probability=ta_probability,
            reason=f"fused probability {fused:.4f}",
        )
