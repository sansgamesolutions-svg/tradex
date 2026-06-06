from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from tradex.config.settings import settings

_OHLCV = {"open", "high", "low", "close", "volume"}


def build_features(df: pd.DataFrame) -> pd.DataFrame:
    """Derive model-ready features from an OHLCV+indicators DataFrame.

    OHLCV columns are excluded from the output to prevent data leakage.
    """
    df = df.copy()
    df["returns"] = df["close"].pct_change()
    df["log_returns"] = np.log(df["close"] / df["close"].shift(1))
    df["hl_range"] = (df["high"] - df["low"]) / df["close"]
    df["oc_range"] = (df["close"] - df["open"]) / df["open"]

    indicator_cols = [c for c in df.columns if c not in _OHLCV]
    return df[indicator_cols].dropna()


def make_target(df: pd.DataFrame, horizon: int | None = None) -> pd.Series:
    """Binary target: 1 if close is higher *horizon* candles ahead, else 0."""
    h = horizon or settings.prediction_horizon
    future = df["close"].shift(-h)
    return (future > df["close"]).astype(int).dropna()


def train_test_split(
    X: pd.DataFrame, y: pd.Series
) -> tuple[pd.DataFrame, pd.DataFrame, pd.Series, pd.Series]:
    idx = X.index.intersection(y.index)
    X, y = X.loc[idx], y.loc[idx]
    split = int(len(X) * settings.train_test_split)
    return X.iloc[:split], X.iloc[split:], y.iloc[:split], y.iloc[split:]


def scale(
    X_train: pd.DataFrame, X_test: pd.DataFrame
) -> tuple[pd.DataFrame, pd.DataFrame, StandardScaler]:
    scaler = StandardScaler()
    X_tr = pd.DataFrame(scaler.fit_transform(X_train), index=X_train.index, columns=X_train.columns)
    X_te = pd.DataFrame(scaler.transform(X_test), index=X_test.index, columns=X_test.columns)
    return X_tr, X_te, scaler
