from __future__ import annotations

import json
from dataclasses import dataclass
from pathlib import Path

DEFAULT_FEATURE_CONFIG_PATH = (
    Path(__file__).resolve().parents[2] / "config" / "features" / "default.json"
)

_GROUPS = ("price", "trend", "momentum", "volatility", "volume")


@dataclass(frozen=True)
class FeatureConfig:
    enabled: frozenset[str]
    lag_periods: tuple[int, ...]
    lag_features: tuple[str, ...]

    @classmethod
    def load(cls, path: Path) -> FeatureConfig:
        data = json.loads(Path(path).read_text())
        enabled: set[str] = set()
        for group in _GROUPS:
            for name, cfg in data.get(group, {}).items():
                if cfg.get("enabled", True):
                    enabled.add(name)
        lags = data.get("lags", {})
        lags_on = bool(lags.get("enabled", False))
        return cls(
            enabled=frozenset(enabled),
            lag_periods=tuple(int(p) for p in lags.get("periods", [])) if lags_on else (),
            lag_features=tuple(lags.get("features", [])) if lags_on else (),
        )

    @classmethod
    def default(cls) -> FeatureConfig:
        return cls.load(DEFAULT_FEATURE_CONFIG_PATH)
