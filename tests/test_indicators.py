import pandas as pd

from tradex.indicators.technical import add_indicators, ta_signal


def test_add_indicators_appends_columns(ohlcv_df):
    result = add_indicators(ohlcv_df)
    assert any("rsi" in c for c in result.columns)
    assert any("macd" in c for c in result.columns)
    assert any("ema" in c for c in result.columns)


def test_add_indicators_drops_nans(ohlcv_df):
    result = add_indicators(ohlcv_df)
    assert result.isna().sum().sum() == 0


def test_ta_signal_in_range(ohlcv_df):
    df = add_indicators(ohlcv_df)
    score = ta_signal(df)
    assert -1.0 <= score <= 1.0


def test_ta_signal_empty_returns_zero():
    assert ta_signal(pd.DataFrame()) == 0.0
