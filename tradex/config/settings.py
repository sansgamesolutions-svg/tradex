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
    ta_only_signal_threshold: float = 0.65
    model_weight: float = 0.6
    ta_weight: float = 0.4
    decision_policy_version: str = "2.0"

    # Storage backend: "local" or "s3"
    storage_backend: str = "local"
    s3_bucket: str = ""
    s3_prefix: str = "tradex"
    s3_endpoint_url: str = ""  # empty = real AWS; set to http://minio:9000 for MinIO

    # Scheduler (comma-separated assets for daily batch predictions)
    schedule_assets: list[str] = field(default_factory=list)
    schedule_hour: int = 9
    schedule_model: str = "xgboost"

    # Interactive Brokers TWS / Gateway
    ibkr_host: str = "127.0.0.1"
    ibkr_port: int = 7497
    ibkr_client_id: int = 10
    ibkr_timeout: float = 4.0

    # Kraken spot trading
    kraken_timeout: int = 10_000

    # S&P 500 stock qualification
    stock_min_bars: int = 1_250
    stock_min_feature_samples: int = 1_000
    stock_min_price: float = 5.0
    stock_min_median_dollar_volume: float = 25_000_000.0
    stock_dollar_volume_window: int = 252
    stock_max_missing_session_rate: float = 0.01
    stock_max_stale_sessions: int = 3
    stock_min_minority_class_rate: float = 0.35
    stock_walk_forward_folds: int = 4
    stock_walk_forward_initial_fraction: float = 0.60
    stock_min_median_roc_auc: float = 0.52
    stock_min_median_balanced_accuracy: float = 0.51
    stock_min_folds_beating_baseline: int = 3

    # Kraken USD spot crypto qualification
    crypto_min_bars: int = 700
    crypto_min_feature_samples: int = 500
    crypto_min_median_quote_volume: float = 1_000_000.0
    crypto_quote_volume_window: int = 90
    crypto_max_missing_day_rate: float = 0.01
    crypto_max_stale_days: int = 2
    crypto_min_minority_class_rate: float = 0.35
    crypto_walk_forward_folds: int = 4
    crypto_walk_forward_initial_fraction: float = 0.60
    crypto_min_median_roc_auc: float = 0.52
    crypto_min_median_balanced_accuracy: float = 0.51
    crypto_min_folds_beating_baseline: int = 3

    # One-day automated trading drill
    drill_data_dir: Path = field(default_factory=lambda: ROOT / "data" / "drill")
    drill_initial_capital: float = 5_000.0
    drill_max_position_cost: float = 500.0
    drill_max_open_positions: int = 2
    drill_stop_loss_rate: float = 0.01
    drill_take_profit_rate: float = 0.02
    drill_max_drawdown_rate: float = 0.01
    drill_max_price_age_minutes: int = 10
    drill_max_future_seconds: int = 60
    drill_min_quote_coverage: float = 0.60
    drill_max_symbol_failures: int = 3
    drill_stock_slippage_rate: float = 0.0002
    drill_stock_fixed_fee: float = 0.35
    drill_crypto_slippage_rate: float = 0.0005
    drill_crypto_fee_rate: float = 0.004

    @classmethod
    def load(cls) -> Settings:
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

        if "drill_data_dir" in data:
            path = Path(data["drill_data_dir"])
            data["drill_data_dir"] = path if path.is_absolute() else ROOT / path

        return cls(**{k: v for k, v in data.items() if k in field_names})


settings = Settings.load()
