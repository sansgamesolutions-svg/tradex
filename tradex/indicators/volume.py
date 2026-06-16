from __future__ import annotations

import pandas as pd
import pandas_ta  # noqa: F401

from tradex.strategy.schema import VolumeGateConfig


def assess_volume(df: pd.DataFrame, cfg: VolumeGateConfig | None = None) -> VolumeAssessment:
    if cfg is None:
        cfg = VolumeGateConfig()

    _neutral = VolumeAssessment(
        volume_ratio=1.0,
        obv_rising=False,
        obv_divergence_bull=False,
        obv_divergence_bear=False,
        volume_ratio_min=cfg.volume_ratio_min,
        require_obv=cfg.require_obv_confirmation,
    )

    if df.empty or len(df) < 22:
        return _neutral

    work = df.copy()
    work.columns = [c.lower() for c in work.columns]

    # Volume ratio: current vs 20-period average
    volume_ratio = 1.0
    if "volume" in work.columns:
        vol_ma = work["volume"].rolling(20).mean().iloc[-1]
        if vol_ma and vol_ma > 0:
            volume_ratio = float(work["volume"].iloc[-1]) / float(vol_ma)

    # OBV slope and divergence
    obv_rising = False
    obv_divergence_bull = False
    obv_divergence_bear = False
    obv_series = work.ta.obv()
    if obv_series is not None and not obv_series.empty and len(obv_series) >= 5:
        obv_rising = float(obv_series.iloc[-1]) > float(obv_series.iloc[-5])

        if len(obv_series) >= 10:
            price_lower_low = float(work["close"].iloc[-1]) < float(work["close"].iloc[-10])
            obv_higher_low = float(obv_series.iloc[-1]) > float(obv_series.iloc[-10])
            obv_divergence_bull = price_lower_low and obv_higher_low

            price_higher_high = float(work["close"].iloc[-1]) > float(work["close"].iloc[-10])
            obv_lower_high = float(obv_series.iloc[-1]) < float(obv_series.iloc[-10])
            obv_divergence_bear = price_higher_high and obv_lower_high

    return VolumeAssessment(
        volume_ratio=volume_ratio,
        obv_rising=obv_rising,
        obv_divergence_bull=obv_divergence_bull,
        obv_divergence_bear=obv_divergence_bear,
        volume_ratio_min=cfg.volume_ratio_min,
        require_obv=cfg.require_obv_confirmation,
    )


class VolumeAssessment:
    __slots__ = (
        "volume_ratio",
        "obv_rising",
        "obv_divergence_bull",
        "obv_divergence_bear",
        "_volume_ratio_min",
        "_require_obv",
    )

    def __init__(
        self,
        volume_ratio: float,
        obv_rising: bool,
        obv_divergence_bull: bool,
        obv_divergence_bear: bool,
        volume_ratio_min: float = 1.5,
        require_obv: bool = True,
    ) -> None:
        self.volume_ratio = volume_ratio
        self.obv_rising = obv_rising
        self.obv_divergence_bull = obv_divergence_bull
        self.obv_divergence_bear = obv_divergence_bear
        self._volume_ratio_min = volume_ratio_min
        self._require_obv = require_obv

    @property
    def bullish_gate(self) -> bool:
        volume_ok = self.volume_ratio >= self._volume_ratio_min
        if self._require_obv:
            return volume_ok and (self.obv_rising or self.obv_divergence_bull)
        return volume_ok

    @property
    def bearish_gate(self) -> bool:
        volume_ok = self.volume_ratio >= self._volume_ratio_min
        if self._require_obv:
            return volume_ok and (not self.obv_rising or self.obv_divergence_bear)
        return volume_ok

    @property
    def __dict__(self) -> dict:
        return {
            "volume_ratio": self.volume_ratio,
            "obv_rising": self.obv_rising,
            "obv_divergence_bull": self.obv_divergence_bull,
            "obv_divergence_bear": self.obv_divergence_bear,
            "bullish_gate": self.bullish_gate,
            "bearish_gate": self.bearish_gate,
        }
