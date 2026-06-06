from __future__ import annotations

import os
from dataclasses import dataclass, field, fields
from pathlib import Path

import yaml

ROOT = Path(__file__).resolve().parents[2]
CACHE_DIR = ROOT / "data" / "cache"
ARTIFACTS_DIR = ROOT / "models" / "artifacts"


@dataclass
class Settings:
    # Paths (used by local storage backend)
    cache_dir: Path = field(default_factory=lambda: CACHE_DIR)
    artifacts_dir: Path = field(default_factory=lambda: ARTIFACTS_DIR)

    # Model behaviour
    default_timeframe: str = "1d"
    lookback_periods: int = 60
    prediction_horizon: int = 1
    train_test_split: float = 0.8
    signal_threshold: float = 0.55
    model_weight: float = 0.6
    ta_weight: float = 0.4

    # Storage backend: "local" or "s3"
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_prefix: str = "tradex"
    s3_endpoint_url: str = ""   # empty = real AWS; set to http://minio:9000 for MinIO

    # Scheduler (comma-separated assets for daily batch predictions)
    schedule_assets: list[str] = field(default_factory=list)
    schedule_hour: int = 9
    schedule_model: str = "xgboost"

    @classmethod
    def load(cls) -> "Settings":
        cfg_file = ROOT / "config.yaml"
        data: dict = {}
        if cfg_file.exists():
            with cfg_file.open() as f:
                data = yaml.safe_load(f) or {}

        field_names = {f.name for f in fields(cls)}
        for name in field_names:
            env_val = os.getenv(f"TRADEX_{name.upper()}")
            if env_val is not None:
                data[name] = env_val

        # Coerce comma-separated env string → list
        if "schedule_assets" in data and isinstance(data["schedule_assets"], str):
            data["schedule_assets"] = [
                a.strip() for a in data["schedule_assets"].split(",") if a.strip()
            ]

        return cls(**{k: v for k, v in data.items() if k in field_names})


settings = Settings.load()
