from __future__ import annotations

import json
from dataclasses import dataclass, field
from pathlib import Path

DEFAULT_STRATEGY_DIR = Path(__file__).resolve().parents[2] / "config" / "strategies"


@dataclass(frozen=True)
class TrendGateConfig:
    enabled: bool = False
    adx_min: float = 20.0
    require_supertrend: bool = True
    require_higher_highs: bool = False


@dataclass(frozen=True)
class MomentumGateConfig:
    enabled: bool = False
    indicator: str = "roc"  # "roc" | "macd" | "stoch"
    period: int = 10
    min_value: float = 0.0


@dataclass(frozen=True)
class VolumeGateConfig:
    enabled: bool = False
    volume_ratio_min: float = 1.5
    require_obv_confirmation: bool = True


@dataclass(frozen=True)
class VolatilityGateConfig:
    enabled: bool = False
    type: str = "breakout"  # "breakout" | "squeeze"
    atr_multiplier: float = 1.5


@dataclass(frozen=True)
class MeanReversionGateConfig:
    enabled: bool = False
    require_bb_touch: bool = True
    rsi_oversold: float = 35.0
    rsi_overbought: float = 65.0


@dataclass(frozen=True)
class NewsGateConfig:
    enabled: bool = False
    lookback_hours: int = 24
    cache_ttl_minutes: int = 60


@dataclass(frozen=True)
class GatesConfig:
    ta_confirmation: bool = True
    trend: TrendGateConfig = field(default_factory=TrendGateConfig)
    momentum: MomentumGateConfig = field(default_factory=MomentumGateConfig)
    volume: VolumeGateConfig = field(default_factory=VolumeGateConfig)
    volatility: VolatilityGateConfig = field(default_factory=VolatilityGateConfig)
    mean_reversion: MeanReversionGateConfig = field(default_factory=MeanReversionGateConfig)
    news: NewsGateConfig = field(default_factory=NewsGateConfig)


@dataclass(frozen=True)
class TimeframeConfig:
    primary: str = "1d"
    confirmation: tuple[str, ...] = field(default_factory=tuple)
    require_alignment: bool = False


@dataclass(frozen=True)
class PositionSizingConfig:
    mode: str = "fixed"  # "fixed" | "confidence_scaled"
    base_cost: float = 500.0
    min_confidence: float = 0.0
    max_scale: float = 1.0


@dataclass(frozen=True)
class RiskConfig:
    stop_loss_rate: float = 0.01  # fraction of entry price
    take_profit_rate: float = 0.02  # fraction of entry price
    max_drawdown_rate: float = 0.02  # halt entries when equity drops X% from session peak
    daily_loss_limit_rate: float = 0.05  # halt entries when total loss > X% of starting capital
    max_open_positions: int = 2  # per-portfolio concurrent position cap
    max_position_cost: float = 500.0  # hard cap on per-position all-in cost (dollars)


@dataclass(frozen=True)
class StrategyConfig:
    name: str
    version: str
    description: str = ""
    model_weight: float = 0.6
    ta_weight: float = 0.4
    ml_ta_threshold: float = 0.55
    ta_only_threshold: float = 0.65
    timeframes: TimeframeConfig = field(default_factory=TimeframeConfig)
    position_sizing: PositionSizingConfig = field(default_factory=PositionSizingConfig)
    risk: RiskConfig = field(default_factory=RiskConfig)
    gates: GatesConfig = field(default_factory=GatesConfig)

    def position_scale(self, confidence: float) -> float:
        """Return a cost multiplier in [0, max_scale] based on signal confidence."""
        cfg = self.position_sizing
        if cfg.mode != "confidence_scaled":
            return 1.0
        if confidence < cfg.min_confidence:
            return 0.0
        return min(confidence * cfg.max_scale, cfg.max_scale)

    @classmethod
    def load(cls, path: Path) -> StrategyConfig:
        data = json.loads(Path(path).read_text())
        return cls._from_dict(data)

    @classmethod
    def default(cls) -> StrategyConfig:
        return cls.load(DEFAULT_STRATEGY_DIR / "default.json")

    @classmethod
    def _from_dict(cls, d: dict) -> StrategyConfig:
        weights = d.get("weights", {})
        thresholds = d.get("thresholds", {})
        tf = d.get("timeframes", {})
        ps = d.get("position_sizing", {})
        r = d.get("risk", {})
        g = d.get("gates", {})

        return cls(
            name=d["name"],
            version=d["version"],
            description=d.get("description", ""),
            model_weight=float(weights.get("model", 0.6)),
            ta_weight=float(weights.get("ta", 0.4)),
            ml_ta_threshold=float(thresholds.get("ml_ta", 0.55)),
            ta_only_threshold=float(thresholds.get("ta_only", 0.65)),
            timeframes=TimeframeConfig(
                primary=tf.get("primary", "1d"),
                confirmation=tuple(tf.get("confirmation", [])),
                require_alignment=bool(tf.get("require_alignment", False)),
            ),
            position_sizing=PositionSizingConfig(
                mode=ps.get("mode", "fixed"),
                base_cost=float(ps.get("base_cost", 500.0)),
                min_confidence=float(ps.get("min_confidence", 0.0)),
                max_scale=float(ps.get("max_scale", 1.0)),
            ),
            risk=RiskConfig(
                stop_loss_rate=float(r.get("stop_loss_rate", 0.01)),
                take_profit_rate=float(r.get("take_profit_rate", 0.02)),
                max_drawdown_rate=float(r.get("max_drawdown_rate", 0.02)),
                daily_loss_limit_rate=float(r.get("daily_loss_limit_rate", 0.05)),
                max_open_positions=int(r.get("max_open_positions", 2)),
                max_position_cost=float(r.get("max_position_cost", 500.0)),
            ),
            gates=_gates_from_dict(g),
        )


def _gates_from_dict(g: dict) -> GatesConfig:
    def _sub(key: str, defaults: dict) -> dict:
        src = g.get(key, {})
        return {**defaults, **src}

    trend = _sub("trend", {})
    mom = _sub("momentum", {})
    vol = _sub("volume", {})
    vlt = _sub("volatility", {})
    mr = _sub("mean_reversion", {})
    news = _sub("news", {})

    return GatesConfig(
        ta_confirmation=bool(g.get("ta_confirmation", True)),
        trend=TrendGateConfig(
            enabled=bool(trend.get("enabled", False)),
            adx_min=float(trend.get("adx_min", 20.0)),
            require_supertrend=bool(trend.get("require_supertrend", True)),
            require_higher_highs=bool(trend.get("require_higher_highs", False)),
        ),
        momentum=MomentumGateConfig(
            enabled=bool(mom.get("enabled", False)),
            indicator=str(mom.get("indicator", "roc")),
            period=int(mom.get("period", 10)),
            min_value=float(mom.get("min_value", 0.0)),
        ),
        volume=VolumeGateConfig(
            enabled=bool(vol.get("enabled", False)),
            volume_ratio_min=float(vol.get("volume_ratio_min", 1.5)),
            require_obv_confirmation=bool(vol.get("require_obv_confirmation", True)),
        ),
        volatility=VolatilityGateConfig(
            enabled=bool(vlt.get("enabled", False)),
            type=str(vlt.get("type", "breakout")),
            atr_multiplier=float(vlt.get("atr_multiplier", 1.5)),
        ),
        mean_reversion=MeanReversionGateConfig(
            enabled=bool(mr.get("enabled", False)),
            require_bb_touch=bool(mr.get("require_bb_touch", True)),
            rsi_oversold=float(mr.get("rsi_oversold", 35.0)),
            rsi_overbought=float(mr.get("rsi_overbought", 65.0)),
        ),
        news=NewsGateConfig(
            enabled=bool(news.get("enabled", False)),
            lookback_hours=int(news.get("lookback_hours", 24)),
            cache_ttl_minutes=int(news.get("cache_ttl_minutes", 60)),
        ),
    )
