from tradex.data.preprocessor import build_features, make_target, train_test_split


def test_build_features_excludes_ohlcv(ohlcv_df):
    features = build_features(ohlcv_df)
    for col in ("open", "high", "low", "close", "volume"):
        assert col not in features.columns


def test_build_features_has_derived_cols(ohlcv_df):
    features = build_features(ohlcv_df)
    assert "returns" in features.columns
    assert "log_returns" in features.columns
    assert len(features) > 0


def test_make_target_binary(ohlcv_df):
    target = make_target(ohlcv_df)
    assert set(target.unique()).issubset({0, 1})


def test_train_test_split_proportions(ohlcv_df):
    X = build_features(ohlcv_df)
    y = make_target(ohlcv_df)
    X_train, X_test, y_train, y_test = train_test_split(X, y)
    total = len(X_train) + len(X_test)
    assert abs(len(X_train) / total - 0.8) < 0.02
