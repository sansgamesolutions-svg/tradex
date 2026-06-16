from __future__ import annotations

import pandas as pd
import pandas_ta  # noqa: F401

from tradex.strategy.schema import MomentumGateConfig


def assess_momentum(df: pd.DataFrame, cfg: MomentumGateConfig | None = None) -> MomentumAssessment:
    if cfg is None:
        cfg = MomentumGateConfig()

    _neutral = MomentumAssessment(
        roc=0.0,
        macd_rising=False,
        stoch_crossover_bull=False,
        stoch_crossover_bear=False,
        indicator=cfg.indicator,
        min_value=cfg.min_value,
    )

    if df.empty or len(df) < max(cfg.period + 1, 14):
        return _neutral

    work = df.copy()
    work.columns = [c.lower() for c in work.columns]

    # ROC
    roc = 0.0
    roc_df = work.ta.roc(length=cfg.period)
    if roc_df is not None and not roc_df.empty:
        roc = float(roc_df.iloc[-1])
        roc = 0.0 if roc != roc else roc  # NaN guard

    # MACD histogram slope (rising = last histogram > previous)
    macd_rising = False
    macd_df = work.ta.macd()
    if macd_df is not None and not macd_df.empty:
        macd_df.columns = [c.lower() for c in macd_df.columns]
        hist_col = next((c for c in macd_df.columns if c.startswith("macdh_")), None)
        if hist_col and len(macd_df) >= 2:
            h_last = float(macd_df.iloc[-1][hist_col])
            h_prev = float(macd_df.iloc[-2][hist_col])
            macd_rising = h_last > h_prev and h_last > 0

    # Stochastic crossover
    stoch_crossover_bull = False
    stoch_crossover_bear = False
    stoch_df = work.ta.stoch()
    if stoch_df is not None and not stoch_df.empty:
        stoch_df.columns = [c.lower() for c in stoch_df.columns]
        k_col = next((c for c in stoch_df.columns if c.startswith("stochk_")), None)
        d_col = next((c for c in stoch_df.columns if c.startswith("stochd_")), None)
        if k_col and d_col and len(stoch_df) >= 2:
            k_now = float(stoch_df.iloc[-1][k_col])
            d_now = float(stoch_df.iloc[-1][d_col])
            k_prev = float(stoch_df.iloc[-2][k_col])
            d_prev = float(stoch_df.iloc[-2][d_col])
            stoch_crossover_bull = k_prev <= d_prev and k_now > d_now and k_now < 50
            stoch_crossover_bear = k_prev >= d_prev and k_now < d_now and k_now > 50

    return MomentumAssessment(
        roc=roc,
        macd_rising=macd_rising,
        stoch_crossover_bull=stoch_crossover_bull,
        stoch_crossover_bear=stoch_crossover_bear,
        indicator=cfg.indicator,
        min_value=cfg.min_value,
    )


class MomentumAssessment:
    __slots__ = (
        "roc",
        "macd_rising",
        "stoch_crossover_bull",
        "stoch_crossover_bear",
        "_indicator",
        "_min_value",
    )

    def __init__(
        self,
        roc: float,
        macd_rising: bool,
        stoch_crossover_bull: bool,
        stoch_crossover_bear: bool,
        indicator: str = "roc",
        min_value: float = 0.0,
    ) -> None:
        self.roc = roc
        self.macd_rising = macd_rising
        self.stoch_crossover_bull = stoch_crossover_bull
        self.stoch_crossover_bear = stoch_crossover_bear
        self._indicator = indicator
        self._min_value = min_value

    @property
    def bullish_gate(self) -> bool:
        if self._indicator == "roc":
            return self.roc > self._min_value
        if self._indicator == "macd":
            return self.macd_rising
        if self._indicator == "stoch":
            return self.stoch_crossover_bull
        return True

    @property
    def bearish_gate(self) -> bool:
        if self._indicator == "roc":
            return self.roc < -self._min_value
        if self._indicator == "macd":
            return not self.macd_rising
        if self._indicator == "stoch":
            return self.stoch_crossover_bear
        return True

    @property
    def __dict__(self) -> dict:
        return {
            "roc": self.roc,
            "macd_rising": self.macd_rising,
            "stoch_crossover_bull": self.stoch_crossover_bull,
            "stoch_crossover_bear": self.stoch_crossover_bear,
            "bullish_gate": self.bullish_gate,
            "bearish_gate": self.bearish_gate,
        }
