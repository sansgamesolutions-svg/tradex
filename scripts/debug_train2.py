"""Reproduce the exact train endpoint logic and print full traceback."""
import traceback

from tradex.data.fetcher import fetch
from tradex.data.preprocessor import build_features, make_target, train_test_split
from tradex.indicators.technical import add_indicators
from tradex.models import get_model

raw_df = fetch("AAPL", "1d", start="2022-01-01")
raw_df = add_indicators(raw_df)
X = build_features(raw_df)
y = make_target(raw_df)
X_train, X_test, y_train, y_test = train_test_split(X, y)

print(f"X_train: {X_train.shape}, y_train unique: {sorted(y_train.unique().tolist())}")
print(f"X_test:  {X_test.shape},  y_test unique:  {sorted(y_test.unique().tolist())}")

m = get_model("xgboost")
print("\nFitting...")
try:
    m.fit(X_train, y_train)
    print("fit() OK")
except Exception:
    print("fit() FAILED:")
    traceback.print_exc()

print("\nEvaluating...")
try:
    metrics = m.evaluate(X_test, y_test)
    print(f"evaluate() OK: {metrics}")
except Exception:
    print("evaluate() FAILED:")
    traceback.print_exc()

print("\nSaving...")
try:
    key = m.save("AAPL", "1d")
    print(f"save() OK: {key}")
except Exception:
    print("save() FAILED:")
    traceback.print_exc()
