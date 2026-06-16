from __future__ import annotations

import pandas as pd
import pandas_ta  # noqa: F401

from tradex.strategy.schema import MeanReversionGateConfig


def assess_mean_reversion(
    df: pd.DataFrame, cfg: MeanReversionGateConfig | None = None
) -> MeanReversionAssessment:
    if cfg is None:
        cfg = MeanReversionGateConfig()

    _neutral = MeanReversionAssessment(
        rsi=50.0,
        bb_touch_lower=False,
        bb_touch_upper=False,
        z_score=0.0,
        rsi_oversold=cfg.rsi_oversold,
        rsi_overbought=cfg.rsi_overbought,
        require_bb_touch=cfg.require_bb_touch,
    )

    if df.empty or len(df) < 22:
        return _neutral

    work = df.copy()
    work.columns = [c.lower() for c in work.columns]

    # RSI
    rsi = 50.0
    rsi_series = work.ta.rsi(length=14)
    if rsi_series is not None and not rsi_series.empty:
        val = float(rsi_series.iloc[-1])
        rsi = 50.0 if val != val else val

    # Bollinger Bands
    bb_touch_lower = False
    bb_touch_upper = False
    bb_df = work.ta.bbands(length=20, std=2)
    if bb_df is not None and not bb_df.empty:
        bb_df.columns = [c.lower() for c in bb_df.columns]
        upper_col = next((c for c in bb_df.columns if c.startswith("bbu_")), None)
        lower_col = next((c for c in bb_df.columns if c.startswith("bbl_")), None)
        if upper_col and lower_col:
            last_close = float(work["close"].iloc[-1])
            lower = float(bb_df[lower_col].iloc[-1])
            upper = float(bb_df[upper_col].iloc[-1])
            bb_touch_lower = last_close <= lower
            bb_touch_upper = last_close >= upper

    # Z-score: (close - 20d mean) / 20d std
    z_score = 0.0
    if len(work) >= 20:
        closes = work["close"].iloc[-20:]
        mean = float(closes.mean())
        std = float(closes.std())
        if std > 0:
            z_score = (float(work["close"].iloc[-1]) - mean) / std

    return MeanReversionAssessment(
        rsi=rsi,
        bb_touch_lower=bb_touch_lower,
        bb_touch_upper=bb_touch_upper,
        z_score=z_score,
        rsi_oversold=cfg.rsi_oversold,
        rsi_overbought=cfg.rsi_overbought,
        require_bb_touch=cfg.require_bb_touch,
    )


class MeanReversionAssessment:
    __slots__ = (
        "rsi",
        "bb_touch_lower",
        "bb_touch_upper",
        "z_score",
        "_rsi_oversold",
        "_rsi_overbought",
        "_require_bb_touch",
    )

    def __init__(
        self,
        rsi: float,
        bb_touch_lower: bool,
        bb_touch_upper: bool,
        z_score: float,
        rsi_oversold: float = 35.0,
        rsi_overbought: float = 65.0,
        require_bb_touch: bool = True,
    ) -> None:
        self.rsi = rsi
        self.bb_touch_lower = bb_touch_lower
        self.bb_touch_upper = bb_touch_upper
        self.z_score = z_score
        self._rsi_oversold = rsi_oversold
        self._rsi_overbought = rsi_overbought
        self._require_bb_touch = require_bb_touch

    @property
    def bullish_gate(self) -> bool:
        rsi_ok = self.rsi < self._rsi_oversold
        if self._require_bb_touch:
            return self.bb_touch_lower and rsi_ok
        return rsi_ok

    @property
    def bearish_gate(self) -> bool:
        rsi_ok = self.rsi > self._rsi_overbought
        if self._require_bb_touch:
            return self.bb_touch_upper and rsi_ok
        return rsi_ok

    @property
    def __dict__(self) -> dict:
        return {
            "rsi": self.rsi,
            "bb_touch_lower": self.bb_touch_lower,
            "bb_touch_upper": self.bb_touch_upper,
            "z_score": self.z_score,
            "bullish_gate": self.bullish_gate,
            "bearish_gate": self.bearish_gate,
        }
