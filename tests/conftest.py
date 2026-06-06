import numpy as np
import pandas as pd
import pytest


def make_ohlcv(n: int = 300) -> pd.DataFrame:
    idx = pd.date_range("2022-01-01", periods=n, freq="D", tz="UTC")
    close = 100 + np.cumsum(np.random.default_rng(42).standard_normal(n))
    return pd.DataFrame(
        {
            "open": close - 0.3,
            "high": close + 1.0,
            "low": close - 1.0,
            "close": close,
            "volume": np.random.default_rng(0).uniform(1e6, 1e7, n),
        },
        index=idx,
    )


@pytest.fixture
def ohlcv_df():
    return make_ohlcv()


@pytest.fixture
def feature_df():
    n = 200
    rng = np.random.default_rng(7)
    return pd.DataFrame(rng.standard_normal((n, 5)), columns=[f"f{i}" for i in range(5)])


@pytest.fixture
def binary_target(feature_df):
    rng = np.random.default_rng(7)
    return pd.Series(rng.integers(0, 2, len(feature_df)), index=feature_df.index)
