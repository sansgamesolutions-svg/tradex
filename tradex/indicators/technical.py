from __future__ import annotations

import pandas as pd
import pandas_ta  # noqa: F401 - registers the DataFrame .ta accessor


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Append standard technical indicators to an OHLCV DataFrame in-place."""
    df = df.copy()

    # Trend
    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.macd(append=True)  # MACD_12_26_9, MACDh_12_26_9, MACDs_12_26_9

    # Momentum
    df.ta.rsi(length=14, append=True)
    df.ta.stoch(append=True)  # STOCHk_14_3_3, STOCHd_14_3_3

    # Volatility
    df.ta.bbands(length=20, append=True)
    df.ta.atr(length=14, append=True)

    # Volume
    df.ta.obv(append=True)

    df.columns = [c.lower() for c in df.columns]
    return df.dropna()


def ta_signal(df: pd.DataFrame) -> float:
    """Return a TA-based directional score in [-1, 1].

    Positive = bullish bias, negative = bearish bias.
    Score is the mean of individual indicator votes.
    """
    if df.empty:
        return 0.0

    row = df.iloc[-1]
    votes: list[float] = []

    # RSI: oversold → bullish, overbought → bearish
    if "rsi_14" in df.columns:
        rsi = row["rsi_14"]
        if rsi < 30:
            votes.append(1.0)
        elif rsi > 70:
            votes.append(-1.0)
        else:
            votes.append(0.0)

    # MACD histogram direction
    macd_hist = next((c for c in df.columns if c.startswith("macdh_")), None)
    if macd_hist:
        votes.append(1.0 if row[macd_hist] > 0 else -1.0)

    # EMA 20/50 trend alignment
    if "ema_20" in df.columns and "ema_50" in df.columns:
        votes.append(1.0 if row["ema_20"] > row["ema_50"] else -1.0)

    # Price vs Bollinger Bands (partial weight)
    bb_lower = next((c for c in df.columns if c.startswith("bbl_")), None)
    bb_upper = next((c for c in df.columns if c.startswith("bbu_")), None)
    if bb_lower and bb_upper:
        if row["close"] < row[bb_lower]:
            votes.append(0.5)
        elif row["close"] > row[bb_upper]:
            votes.append(-0.5)
        else:
            votes.append(0.0)

    return sum(votes) / len(votes) if votes else 0.0
