from __future__ import annotations

import io
from abc import ABC, abstractmethod

import joblib
import numpy as np
import pandas as pd


class BaseModel(ABC):
    name: str = "base"

    @abstractmethod
    def fit(self, X: pd.DataFrame, y: pd.Series) -> None: ...

    @abstractmethod
    def predict_probabilities(self, X: pd.DataFrame) -> np.ndarray:
        """Return upward-move probabilities for all model-ready samples."""
        ...

    def predict_proba(self, X: pd.DataFrame) -> float:
        """Return the latest probability of an upward move."""
        probabilities = self.predict_probabilities(X)
        if len(probabilities) == 0:
            raise ValueError("Not enough samples to produce a prediction")
        return float(probabilities[-1])

    def predict(self, X: pd.DataFrame) -> int:
        """Return 1 (up) or 0 (down)."""
        return int(self.predict_proba(X) >= 0.5)

    @abstractmethod
    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict[str, float]: ...

    def save(self, asset: str, timeframe: str) -> str:
        from tradex.storage import get_storage

        key = f"models/artifacts/{self.name}_{asset.replace('/', '_')}_{timeframe}.pkl"
        buf = io.BytesIO()
        joblib.dump(self, buf)
        get_storage().put(key, buf.getvalue())
        return key

    @classmethod
    def load(cls, asset: str, timeframe: str) -> BaseModel:
        from tradex.storage import get_storage

        key = f"models/artifacts/{cls.name}_{asset.replace('/', '_')}_{timeframe}.pkl"
        data = get_storage().get(key)
        if data is None:
            raise FileNotFoundError(f"No saved model at '{key}'. Run `tradex train` first.")
        return joblib.load(io.BytesIO(data))
