from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import accuracy_score, roc_auc_score

from tradex.models.base import BaseModel


class RandomForestModel(BaseModel):
    name = "random_forest"

    def __init__(self, n_estimators: int = 200, max_depth: int = 6, **kwargs):
        self._model = RandomForestClassifier(
            n_estimators=n_estimators,
            max_depth=max_depth,
            n_jobs=-1,
            random_state=42,
            **kwargs,
        )

    def _to_numpy(self, X: pd.DataFrame, y: pd.Series | None = None):
        X_arr = X.to_numpy(dtype=np.float32)
        if y is None:
            return X_arr
        y_arr = np.asarray(y, dtype=np.int32)
        return X_arr, y_arr

    def fit(self, X: pd.DataFrame, y: pd.Series) -> None:
        X_arr, y_arr = self._to_numpy(X, y)
        self._model.fit(X_arr, y_arr)

    def predict_proba(self, X: pd.DataFrame) -> float:
        X_arr = self._to_numpy(X)
        return float(self._model.predict_proba(X_arr)[-1, 1])

    def evaluate(self, X: pd.DataFrame, y: pd.Series) -> dict[str, float]:
        X_arr, y_arr = self._to_numpy(X, y)
        preds = self._model.predict(X_arr)
        probas = self._model.predict_proba(X_arr)[:, 1]
        metrics: dict[str, float] = {"accuracy": float(accuracy_score(y_arr, preds))}
        try:
            metrics["roc_auc"] = float(roc_auc_score(y_arr, probas))
        except ValueError:
            metrics["roc_auc"] = float("nan")
        return metrics
