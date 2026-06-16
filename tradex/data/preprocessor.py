from __future__ import annotations

import numpy as np
import pandas as pd
from sklearn.preprocessing import StandardScaler

from tradex.config.settings import settings
from tradex.data.feature_config import FeatureConfig


def build_features(df: pd.DataFrame, config: FeatureConfig | None = None) -> pd.DataFrame:
    """Derive model-ready features from an OHLCV+indicators DataFrame.

    Feature selection and lag configuration are driven by config (default.json).
    All raw OHLCV columns are excluded; only engineered and normalised features remain.
    """
    if config is None:
        config = FeatureConfig.default()

    df = df.copy()
    en = config.enabled
    cols: dict[str, pd.Series] = {}

    # ── price ─────────────────────────────────────────────────────────────
    if "returns" in en:
        cols["returns"] = df["close"].pct_change()
    if "log_returns" in en:
        cols["log_returns"] = np.log(df["close"] / df["close"].shift(1))
    if "hl_range" in en:
        cols["hl_range"] = (df["high"] - df["low"]) / df["close"]
    if "oc_range" in en:
        cols["oc_range"] = (df["close"] - df["open"]) / df["open"]

    # ── trend ─────────────────────────────────────────────────────────────
    if "ema_ratio_price_20" in en and "ema_20" in df.columns:
        cols["ema_ratio_price_20"] = df["close"] / df["ema_20"]
    if "ema_ratio_20_50" in en and {"ema_20", "ema_50"} <= set(df.columns):
        cols["ema_ratio_20_50"] = df["ema_20"] / df["ema_50"]
    if "ema_ratio_50_200" in en and {"ema_50", "ema_200"} <= set(df.columns):
        cols["ema_ratio_50_200"] = df["ema_50"] / df["ema_200"]
    _macd_h = next((c for c in df.columns if c.startswith("macdh_")), None)
    _macd_s = next((c for c in df.columns if c.startswith("macds_")), None)
    if "macd_hist_norm" in en and _macd_h:
        cols["macd_hist_norm"] = df[_macd_h] / df["close"]
    if "macd_signal_norm" in en and _macd_s:
        cols["macd_signal_norm"] = df[_macd_s] / df["close"]

    # ── momentum ──────────────────────────────────────────────────────────
    if "rsi" in en and "rsi_14" in df.columns:
        cols["rsi"] = df["rsi_14"]
    _stoch_k = next((c for c in df.columns if c.startswith("stochk_")), None)
    _stoch_d = next((c for c in df.columns if c.startswith("stochd_")), None)
    if "stoch_k" in en and _stoch_k:
        cols["stoch_k"] = df[_stoch_k]
    if "stoch_d" in en and _stoch_d:
        cols["stoch_d"] = df[_stoch_d]

    # ── volatility ────────────────────────────────────────────────────────
    _atr = next((c for c in df.columns if c.startswith("atrr_")), None)
    _bb_pct = next((c for c in df.columns if c.startswith("bbp_")), None)
    _bb_bw = next((c for c in df.columns if c.startswith("bbb_")), None)
    if "atr_norm" in en and _atr:
        cols["atr_norm"] = df[_atr]
    if "bb_pct_b" in en and _bb_pct:
        cols["bb_pct_b"] = df[_bb_pct]
    if "bb_width" in en and _bb_bw:
        cols["bb_width"] = df[_bb_bw]

    # ── volume ────────────────────────────────────────────────────────────
    if "obv_returns" in en and "obv" in df.columns:
        cols["obv_returns"] = df["obv"].pct_change()

    # ── assemble base frame ───────────────────────────────────────────────
    out = pd.DataFrame(cols, index=df.index)

    # ── lags ──────────────────────────────────────────────────────────────
    if config.lag_periods:
        lag_series = [
            out[fname].shift(p).rename(f"{fname}_lag{p}")
            for fname in config.lag_features
            if fname in out.columns
            for p in config.lag_periods
        ]
        if lag_series:
            out = pd.concat([out, *lag_series], axis=1)

    return out.dropna()


def make_target(df: pd.DataFrame, horizon: int | None = None) -> pd.Series:
    """Binary target: 1 if close is higher *horizon* candles ahead, else 0."""
    h = horizon or settings.prediction_horizon
    future = df["close"].shift(-h)
    valid = future.notna()
    return (future.loc[valid] > df.loc[valid, "close"]).astype(int)


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
