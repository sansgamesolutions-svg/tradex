from __future__ import annotations

import pandas as pd
import pandas_ta  # noqa: F401

from tradex.strategy.schema import VolatilityGateConfig


def assess_volatility(
    df: pd.DataFrame, cfg: VolatilityGateConfig | None = None
) -> VolatilityAssessment:
    if cfg is None:
        cfg = VolatilityGateConfig()

    _neutral = VolatilityAssessment(
        atr=0.0,
        bb_width=0.0,
        bb_squeeze=False,
        atr_breakout_bull=False,
        atr_breakout_bear=False,
        gate_type=cfg.type,
        atr_multiplier=cfg.atr_multiplier,
    )

    if df.empty or len(df) < 22:
        return _neutral

    work = df.copy()
    work.columns = [c.lower() for c in work.columns]

    # ATR
    atr = 0.0
    atr_series = work.ta.atr(length=14)
    if atr_series is not None and not atr_series.empty:
        atr = float(atr_series.iloc[-1])
        atr = 0.0 if atr != atr else atr

    # Bollinger Band width
    bb_width = 0.0
    bb_squeeze = False
    bb_df = work.ta.bbands(length=20, std=2)
    if bb_df is not None and not bb_df.empty:
        bb_df.columns = [c.lower() for c in bb_df.columns]
        upper_col = next((c for c in bb_df.columns if c.startswith("bbu_")), None)
        lower_col = next((c for c in bb_df.columns if c.startswith("bbl_")), None)
        if upper_col and lower_col:
            width_series = bb_df[upper_col] - bb_df[lower_col]
            bb_width = float(width_series.iloc[-1])
            avg_width = float(width_series.rolling(20).mean().iloc[-1])
            if avg_width > 0:
                bb_squeeze = bb_width < avg_width

    # ATR breakout: close moved more than N × ATR from previous close
    atr_breakout_bull = False
    atr_breakout_bear = False
    if atr > 0 and len(work) >= 2:
        prev_close = float(work["close"].iloc[-2])
        last_close = float(work["close"].iloc[-1])
        threshold = cfg.atr_multiplier * atr
        atr_breakout_bull = (last_close - prev_close) > threshold
        atr_breakout_bear = (prev_close - last_close) > threshold

    return VolatilityAssessment(
        atr=atr,
        bb_width=bb_width,
        bb_squeeze=bb_squeeze,
        atr_breakout_bull=atr_breakout_bull,
        atr_breakout_bear=atr_breakout_bear,
        gate_type=cfg.type,
        atr_multiplier=cfg.atr_multiplier,
    )


class VolatilityAssessment:
    __slots__ = (
        "atr",
        "bb_width",
        "bb_squeeze",
        "atr_breakout_bull",
        "atr_breakout_bear",
        "_gate_type",
        "_atr_multiplier",
    )

    def __init__(
        self,
        atr: float,
        bb_width: float,
        bb_squeeze: bool,
        atr_breakout_bull: bool,
        atr_breakout_bear: bool,
        gate_type: str = "breakout",
        atr_multiplier: float = 1.5,
    ) -> None:
        self.atr = atr
        self.bb_width = bb_width
        self.bb_squeeze = bb_squeeze
        self.atr_breakout_bull = atr_breakout_bull
        self.atr_breakout_bear = atr_breakout_bear
        self._gate_type = gate_type
        self._atr_multiplier = atr_multiplier

    @property
    def bullish_gate(self) -> bool:
        if self._gate_type == "breakout":
            return self.atr_breakout_bull
        if self._gate_type == "squeeze":
            return self.bb_squeeze
        return True

    @property
    def bearish_gate(self) -> bool:
        if self._gate_type == "breakout":
            return self.atr_breakout_bear
        if self._gate_type == "squeeze":
            return self.bb_squeeze
        return True

    @property
    def __dict__(self) -> dict:
        return {
            "atr": self.atr,
            "bb_width": self.bb_width,
            "bb_squeeze": self.bb_squeeze,
            "atr_breakout_bull": self.atr_breakout_bull,
            "atr_breakout_bear": self.atr_breakout_bear,
            "bullish_gate": self.bullish_gate,
            "bearish_gate": self.bearish_gate,
        }
