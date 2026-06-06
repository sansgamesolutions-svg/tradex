from __future__ import annotations

import pandas as pd

from tradex.config.settings import settings
from tradex.indicators.technical import ta_signal
from tradex.models.base import BaseModel


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

        Fuses ML probability with TA score. If no trained model is available,
        falls back to TA-only signal.
        """
        ml_prob = self._model.predict_proba(features) if self._model is not None else 0.5

        ta_score = ta_signal(raw_df) if raw_df is not None else 0.0
        ta_prob = (ta_score + 1) / 2  # scale [-1, 1] → [0, 1]

        fused = settings.model_weight * ml_prob + settings.ta_weight * ta_prob

        if fused >= settings.signal_threshold:
            return "BUY"
        if fused <= (1.0 - settings.signal_threshold):
            return "SELL"
        return "HOLD"
