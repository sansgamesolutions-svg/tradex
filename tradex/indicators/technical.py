from __future__ import annotations

from dataclasses import dataclass

import pandas as pd
import pandas_ta  # noqa: F401 - registers the DataFrame .ta accessor


@dataclass(frozen=True)
class TechnicalAssessment:
    score: float
    probability: float
    votes: dict[str, float]
    confirmations: dict[str, bool]

    @property
    def bullish_confirmed(self) -> bool:
        return all(
            (
                self.confirmations["ema_bullish"],
                self.confirmations["macd_bullish"],
                self.confirmations["rsi_below_overbought"],
            )
        )

    @property
    def bearish_confirmed(self) -> bool:
        return all(
            (
                self.confirmations["ema_bearish"],
                self.confirmations["macd_bearish"],
                self.confirmations["rsi_above_oversold"],
            )
        )


def add_indicators(df: pd.DataFrame) -> pd.DataFrame:
    """Append standard technical indicators to an OHLCV DataFrame in-place."""
    df = df.copy()

    df.ta.ema(length=20, append=True)
    df.ta.ema(length=50, append=True)
    df.ta.ema(length=200, append=True)
    df.ta.macd(append=True)
    df.ta.rsi(length=14, append=True)
    df.ta.stoch(append=True)
    df.ta.bbands(length=20, append=True)
    df.ta.atr(length=14, append=True)
    df.ta.obv(append=True)

    df.columns = [column.lower() for column in df.columns]
    return df.dropna()


def assess_technical(df: pd.DataFrame) -> TechnicalAssessment:
    """Return named votes and strict bullish/bearish confirmations."""
    if df.empty:
        return TechnicalAssessment(
            score=0.0,
            probability=0.5,
            votes={},
            confirmations={
                "ema_bullish": False,
                "ema_bearish": False,
                "macd_bullish": False,
                "macd_bearish": False,
                "rsi_below_overbought": False,
                "rsi_above_oversold": False,
            },
        )

    row = df.iloc[-1]
    votes: dict[str, float] = {}

    rsi_present = "rsi_14" in df.columns
    rsi = float(row["rsi_14"]) if rsi_present else 50.0
    if rsi_present:
        if rsi < 30:
            votes["rsi"] = 1.0
        elif rsi > 70:
            votes["rsi"] = -1.0
        else:
            votes["rsi"] = 0.0

    macd_hist = next((column for column in df.columns if column.startswith("macdh_")), None)
    if macd_hist:
        votes["macd"] = 1.0 if row[macd_hist] > 0 else -1.0

    ema_present = "ema_20" in df.columns and "ema_50" in df.columns
    if ema_present:
        votes["ema"] = 1.0 if row["ema_20"] > row["ema_50"] else -1.0

    bb_lower = next((column for column in df.columns if column.startswith("bbl_")), None)
    bb_upper = next((column for column in df.columns if column.startswith("bbu_")), None)
    if bb_lower and bb_upper:
        if row["close"] < row[bb_lower]:
            votes["bollinger"] = 0.5
        elif row["close"] > row[bb_upper]:
            votes["bollinger"] = -0.5
        else:
            votes["bollinger"] = 0.0

    score = sum(votes.values()) / len(votes) if votes else 0.0
    confirmations = {
        "ema_bullish": bool(ema_present and row["ema_20"] > row["ema_50"]),
        "ema_bearish": bool(ema_present and row["ema_20"] < row["ema_50"]),
        "macd_bullish": bool(macd_hist and row[macd_hist] > 0),
        "macd_bearish": bool(macd_hist and row[macd_hist] < 0),
        "rsi_below_overbought": bool(rsi_present and rsi < 70),
        "rsi_above_oversold": bool(rsi_present and rsi > 30),
    }
    return TechnicalAssessment(
        score=score,
        probability=(score + 1.0) / 2.0,
        votes=votes,
        confirmations=confirmations,
    )


def ta_signal(df: pd.DataFrame) -> float:
    """Return a TA-based directional score in [-1, 1]."""
    return assess_technical(df).score
