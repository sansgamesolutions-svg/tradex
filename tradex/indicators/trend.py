from __future__ import annotations

import pandas as pd
import pandas_ta  # noqa: F401

from tradex.strategy.schema import TrendGateConfig


def _default_cfg() -> TrendGateConfig:
    return TrendGateConfig()


def assess_trend(df: pd.DataFrame, cfg: TrendGateConfig | None = None) -> TrendAssessment:
    if cfg is None:
        cfg = _default_cfg()

    _neutral = TrendAssessment(
        adx=0.0,
        trend_direction="SIDEWAYS",
        supertrend_bullish=False,
        higher_highs=False,
        higher_lows=False,
        adx_min=cfg.adx_min,
        require_supertrend=cfg.require_supertrend,
        require_higher_highs=cfg.require_higher_highs,
    )

    if df.empty or len(df) < 20:
        return _neutral

    work = df.copy()
    work.columns = [c.lower() for c in work.columns]

    # ADX
    adx_df = work.ta.adx(length=14)
    if adx_df is None or adx_df.empty:
        return _neutral
    adx_df.columns = [c.lower() for c in adx_df.columns]
    adx_col = next((c for c in adx_df.columns if c.startswith("adx_")), None)
    dmp_col = next((c for c in adx_df.columns if c.startswith("dmp_")), None)
    dmn_col = next((c for c in adx_df.columns if c.startswith("dmn_")), None)
    if not all([adx_col, dmp_col, dmn_col]):
        return _neutral

    last = adx_df.iloc[-1]
    adx = float(last[adx_col])
    dmp = float(last[dmp_col])
    dmn = float(last[dmn_col])

    if dmp > dmn:
        trend_direction = "UP"
    elif dmn > dmp:
        trend_direction = "DOWN"
    else:
        trend_direction = "SIDEWAYS"

    # SuperTrend
    supertrend_bullish = False
    st_df = work.ta.supertrend(length=7, multiplier=3.0)
    if st_df is not None and not st_df.empty:
        st_df.columns = [c.lower() for c in st_df.columns]
        dir_col = next((c for c in st_df.columns if c.startswith("supert_d_")), None)
        if dir_col:
            supertrend_bullish = float(st_df.iloc[-1][dir_col]) > 0

    # Higher-highs / higher-lows using last 3 swing points (simplified: last 3 bars)
    higher_highs = False
    higher_lows = False
    if len(work) >= 3:
        recent_highs = work["high"].iloc[-3:].values
        recent_lows = work["low"].iloc[-3:].values
        higher_highs = bool(recent_highs[-1] > recent_highs[-2] > recent_highs[-3])
        higher_lows = bool(recent_lows[-1] > recent_lows[-2] > recent_lows[-3])

    return TrendAssessment(
        adx=adx,
        trend_direction=trend_direction,
        supertrend_bullish=supertrend_bullish,
        higher_highs=higher_highs,
        higher_lows=higher_lows,
        adx_min=cfg.adx_min,
        require_supertrend=cfg.require_supertrend,
        require_higher_highs=cfg.require_higher_highs,
    )


class TrendAssessment:
    __slots__ = (
        "adx",
        "trend_direction",
        "supertrend_bullish",
        "higher_highs",
        "higher_lows",
        "_adx_min",
        "_require_supertrend",
        "_require_higher_highs",
    )

    def __init__(
        self,
        adx: float,
        trend_direction: str,
        supertrend_bullish: bool,
        higher_highs: bool,
        higher_lows: bool,
        adx_min: float = 20.0,
        require_supertrend: bool = True,
        require_higher_highs: bool = False,
    ) -> None:
        self.adx = adx
        self.trend_direction = trend_direction
        self.supertrend_bullish = supertrend_bullish
        self.higher_highs = higher_highs
        self.higher_lows = higher_lows
        self._adx_min = adx_min
        self._require_supertrend = require_supertrend
        self._require_higher_highs = require_higher_highs

    @property
    def bullish_gate(self) -> bool:
        ok = self.adx >= self._adx_min and self.trend_direction == "UP"
        if self._require_supertrend:
            ok = ok and self.supertrend_bullish
        if self._require_higher_highs:
            ok = ok and self.higher_highs and self.higher_lows
        return ok

    @property
    def bearish_gate(self) -> bool:
        ok = self.adx >= self._adx_min and self.trend_direction == "DOWN"
        if self._require_supertrend:
            ok = ok and not self.supertrend_bullish
        return ok

    @property
    def __dict__(self) -> dict:
        return {
            "adx": self.adx,
            "trend_direction": self.trend_direction,
            "supertrend_bullish": self.supertrend_bullish,
            "higher_highs": self.higher_highs,
            "higher_lows": self.higher_lows,
            "bullish_gate": self.bullish_gate,
            "bearish_gate": self.bearish_gate,
        }
