from __future__ import annotations

import pandas as pd

from tradex.decision import DecisionEngine
from tradex.indicators.technical import ta_signal
from tradex.models.base import BaseModel

_engine = DecisionEngine()


class SignalCombiner:
    """Fuses an ML model's probability output with TA-based directional score."""

    def __init__(
        self,
        model_name: str = "xgboost",
        asset: str | None = None,
        timeframe: str = "1d",
    ):
        self.model_name = model_name
        self._model: BaseModel | None = None

        if asset:
            from tradex.models import _REGISTRY

            cls = _REGISTRY.get(model_name)
            if cls is not None:
                try:
                    self._model = cls.load(asset, timeframe)
                except FileNotFoundError:
                    pass  # fall back to TA-only until model is trained

    def predict(self, features: pd.DataFrame, raw_df: pd.DataFrame | None = None) -> str:
        """Return 'BUY', 'SELL', or 'HOLD'.

        Fuses ML probability with TA score via DecisionEngine. Falls back to
        TA-only when no trained model artifact is available.
        """
        ml_prob = self._model.predict_proba(features) if self._model is not None else None
        ta_score = ta_signal(raw_df) if raw_df is not None else 0.0
        ta_prob = (ta_score + 1) / 2  # scale [-1, 1] → [0, 1]
        return _engine.decide(ml_probability=ml_prob, ta_probability=ta_prob).signal
