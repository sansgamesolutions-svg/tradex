from tradex.signals.combiner import SignalCombiner

_VALID = {"BUY", "SELL", "HOLD"}


def test_combiner_no_model_returns_valid_signal(feature_df):
    combiner = SignalCombiner(model_name="xgboost")  # no asset → no saved model
    decision = combiner.predict(feature_df)
    assert decision.signal in _VALID


def test_combiner_with_raw_df(ohlcv_df, feature_df):
    from tradex.indicators.technical import add_indicators

    raw = add_indicators(ohlcv_df)
    # feature_df and raw may differ in length; test that it doesn't raise
    combiner = SignalCombiner(model_name="xgboost")
    decision = combiner.predict(feature_df, raw_df=raw)
    assert decision.signal in _VALID
