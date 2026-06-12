import pandas as pd

from tradex.indicators.technical import add_indicators, assess_technical, ta_signal


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


def test_strict_ta_confirmation_requires_all_named_votes():
    frame = pd.DataFrame(
        {
            "close": [100.0],
            "ema_20": [105.0],
            "ema_50": [100.0],
            "macdh_12_26_9": [-1.0],
            "rsi_14": [50.0],
        }
    )

    assessment = assess_technical(frame)

    assert assessment.votes["ema"] == 1.0
    assert assessment.bullish_confirmed is False
    assert assessment.confirmations["macd_bullish"] is False


def test_overbought_rsi_vetoes_ta_only_bullish_confirmation():
    frame = pd.DataFrame(
        {
            "close": [100.0],
            "ema_20": [105.0],
            "ema_50": [100.0],
            "macdh_12_26_9": [1.0],
            "rsi_14": [75.0],
        }
    )

    assert assess_technical(frame).bullish_confirmed is False
