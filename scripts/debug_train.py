"""Diagnostic script — print data shapes and label distributions for AAPL training."""

from tradex.data.fetcher import fetch
from tradex.data.preprocessor import build_features, make_target, train_test_split
from tradex.indicators.technical import add_indicators

raw_df = fetch("AAPL", "1d", start="2022-01-01", force_refresh=True)
print(f"fetched : {raw_df.shape}  |  {raw_df.index[0].date()} to {raw_df.index[-1].date()}")

raw_df = add_indicators(raw_df)
print(f"after TA: {raw_df.shape}")

X = build_features(raw_df)
y = make_target(raw_df)
print(f"X shape : {X.shape}")
print(f"y shape : {y.shape}  unique={sorted(y.unique().tolist())}")
print(f"y counts: {y.value_counts().to_dict()}")

X_tr, X_te, y_tr, y_te = train_test_split(X, y)
print(f"\ntrain split ({len(y_tr)} rows):")
print(f"  y_train unique : {sorted(y_tr.unique().tolist())}")
print(f"  y_train counts : {y_tr.value_counts().to_dict()}")
print(f"\ntest split ({len(y_te)} rows):")
print(f"  y_test unique  : {sorted(y_te.unique().tolist())}")
print(f"  y_test counts  : {y_te.value_counts().to_dict()}")
