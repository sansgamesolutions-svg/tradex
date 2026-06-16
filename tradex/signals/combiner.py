from __future__ import annotations

import pandas as pd

from tradex.decision import Decision, DecisionEngine
from tradex.indicators.technical import assess_technical
from tradex.models.base import BaseModel
from tradex.strategy.schema import StrategyConfig


class SignalCombiner:
    """Fuses an ML model's probability output with TA-based directional score."""

    def __init__(
        self,
        model_name: str = "xgboost",
        asset: str | None = None,
        timeframe: str = "1d",
        strategy: StrategyConfig | None = None,
    ):
        self.model_name = model_name
        self._asset = asset
        self._timeframe = timeframe
        self._strategy = strategy or StrategyConfig.default()
        self._model: BaseModel | None = None

        if asset:
            from tradex.models import _REGISTRY

            cls = _REGISTRY.get(model_name)
            if cls is not None:
                try:
                    self._model = cls.load(asset, timeframe)
                except FileNotFoundError:
                    pass  # fall back to TA-only until model is trained

    def predict(self, features: pd.DataFrame, raw_df: pd.DataFrame | None = None) -> Decision:
        """Return a Decision fusing ML probability with TA score and all enabled gates.

        Falls back to TA-only when no trained model artifact is available.
        """
        cfg = self._strategy
        ml_prob = self._model.predict_proba(features) if self._model is not None else None
        assessment = (
            assess_technical(raw_df) if raw_df is not None else assess_technical(pd.DataFrame())
        )

        bullish = assessment.bullish_confirmed if cfg.gates.ta_confirmation else True
        bearish = assessment.bearish_confirmed if cfg.gates.ta_confirmation else True
        details: dict = dict(assessment.confirmations)

        df = raw_df if raw_df is not None else pd.DataFrame()

        # Apply each enabled gate — all must pass for the signal direction
        if cfg.gates.trend.enabled:
            from tradex.indicators.trend import assess_trend

            trend = assess_trend(df, cfg.gates.trend)
            bullish = bullish and trend.bullish_gate
            bearish = bearish and trend.bearish_gate
            details["trend"] = trend.__dict__

        if cfg.gates.momentum.enabled:
            from tradex.indicators.momentum import assess_momentum

            mom = assess_momentum(df, cfg.gates.momentum)
            bullish = bullish and mom.bullish_gate
            bearish = bearish and mom.bearish_gate
            details["momentum"] = mom.__dict__

        if cfg.gates.volume.enabled:
            from tradex.indicators.volume import assess_volume

            vol = assess_volume(df, cfg.gates.volume)
            bullish = bullish and vol.bullish_gate
            bearish = bearish and vol.bearish_gate
            details["volume"] = vol.__dict__

        if cfg.gates.volatility.enabled:
            from tradex.indicators.volatility import assess_volatility

            vlt = assess_volatility(df, cfg.gates.volatility)
            bullish = bullish and vlt.bullish_gate
            bearish = bearish and vlt.bearish_gate
            details["volatility"] = vlt.__dict__

        if cfg.gates.mean_reversion.enabled:
            from tradex.indicators.mean_reversion import assess_mean_reversion

            mr = assess_mean_reversion(df, cfg.gates.mean_reversion)
            bullish = bullish and mr.bullish_gate
            bearish = bearish and mr.bearish_gate
            details["mean_reversion"] = mr.__dict__

        if cfg.gates.news.enabled and self._asset:
            from tradex.config.settings import settings
            from tradex.data.news import fetch_news
            from tradex.indicators.sentiment import assess_sentiment

            headlines = fetch_news(
                self._asset, settings.finnhub_api_key, cfg.gates.news.lookback_hours
            )
            news = assess_sentiment(headlines, cfg.gates.news)
            bullish = bullish and news.bullish_gate
            bearish = bearish and news.bearish_gate
            details["news"] = news.__dict__

        engine = DecisionEngine(
            model_weight=cfg.model_weight,
            ta_weight=cfg.ta_weight,
            signal_threshold=cfg.ml_ta_threshold,
            ta_only_threshold=cfg.ta_only_threshold,
            policy_version=f"{cfg.name}-{cfg.version}",
        )
        decision = engine.decide(
            ml_probability=ml_prob,
            ta_probability=assessment.probability,
            bullish_confirmed=bullish,
            bearish_confirmed=bearish,
            confirmation_details=details,
        )

        # Multi-timeframe alignment veto (post-decision)
        if cfg.timeframes.require_alignment and decision.signal != "HOLD" and self._asset:
            from tradex.signals.multitf import check_timeframe_alignment

            aligned = check_timeframe_alignment(
                self._asset,
                decision.signal,
                list(cfg.timeframes.confirmation),
                self.model_name,
            )
            if not aligned:
                decision = Decision(
                    signal="HOLD",
                    fused_probability=decision.fused_probability,
                    confidence=decision.confidence,
                    threshold_used=decision.threshold_used,
                    ml_probability=decision.ml_probability,
                    ta_probability=decision.ta_probability,
                    source=decision.source,
                    policy_version=decision.policy_version,
                    confirmation_details=decision.confirmation_details,
                    reason=decision.reason + " [vetoed: MTF misalignment]",
                )

        return decision
