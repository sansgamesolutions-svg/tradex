from __future__ import annotations

import io
import pickle

import pandas as pd


def _key(asset: str, timeframe: str) -> str:
    safe = asset.replace("/", "_").replace("\\", "_")
    return f"data/cache/{safe}_{timeframe}.pkl"


def load(asset: str, timeframe: str) -> pd.DataFrame | None:
    from tradex.storage import get_storage

    data = get_storage().get(_key(asset, timeframe))
    return pickle.loads(data) if data is not None else None


def save(asset: str, timeframe: str, df: pd.DataFrame) -> None:
    from tradex.storage import get_storage

    get_storage().put(_key(asset, timeframe), pickle.dumps(df))
