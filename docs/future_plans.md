# Future Plans

Captured 2026-06-16. Revisit in a couple of days.

---

## Highest Impact

### 1. Fix backtester look-ahead bias
The biggest issue in the codebase. `Backtester.run()` loads a pre-trained artifact fitted on the full test period — all backtest numbers (+342% AAPL, +171% BTC) are inflated. Replace with a walk-forward loop: at each step, retrain on data up to bar `i`, predict bar `i+1`. This is the only honest performance estimate and will likely cut returns significantly — which is the point.

### 2. Crypto model has negative edge
BTC ROC-AUC was 0.43 with the new feature set (worse than random). Daily 1-bar crypto prediction is near white noise. Options:
- Switch to a shorter horizon (`prediction_horizon = 3`) for crypto
- Use 4h timeframe instead of 1d for crypto
- Apply the `mean-reversion` strategy preset for crypto in the drill (lower thresholds)

### 3. Drill: all 10 symbols fall to TA_ONLY
The drill qualification window only covers ~18 months of crypto history — barely enough for 4 folds. The "≥3 folds beat baseline" criterion fails for every symbol today. Two concrete fixes:
- Lower crypto fold requirement from 3 → 2 in `DrillSignalService`
- Use per-asset-class strategy in `DrillEngine` (momentum for crypto, default for stocks)

---

## Model Quality

### 4. Feature importance analysis
With 40 features, run `model.feature_importances_` after training and prune near-zero contributors. Likely weak features: `log_returns` (highly correlated with `returns`), some 5-bar lags. Fewer, stronger features typically improve out-of-sample generalisation.

### 5. Add rolling statistics
`rolling_vol` (20-bar std of returns) and `returns_z` (returns / rolling_vol) are strong regime-detection features missing from the current set. They help the model distinguish trending vs mean-reverting regimes.

### 6. Hyperparameter tuning
XGBoost uses defaults (`n_estimators=200, max_depth=5, lr=0.05`). A time-series cross-validated grid search over `max_depth` (3–7) and `learning_rate` (0.01–0.1) on qualification data would improve walk-forward ROC-AUC scores meaningfully.

---

## Infrastructure

### 7. Tests for the new feature pipeline
`test_data.py` was written before `FeatureConfig` and the new `build_features()`. Add tests that:
- Confirm all 40 columns are produced with the default config
- Confirm disabling a feature group removes those columns from the output
- Confirm no NaNs reach the model

### 8. Update CLAUDE.md
The architecture section doesn't yet mention `FeatureConfig` or `config/features/`. Update the data flow section to reflect the current `build_features()` implementation.

### 9. Per-asset-class strategy selection in drill
`DrillEngine` uses one `StrategyConfig` for both STOCK and CRYPTO portfolios. Wire in separate strategies — e.g. `momentum` preset for crypto (ROC gate enabled, higher threshold), `default` for stocks. `DrillEngine.__init__` could accept `stock_strategy` and `crypto_strategy` params.

---

## Longer Term

### 10. Live execution validation
The IBKR and Kraken broker adapters exist but have never been end-to-end tested. A paper-trading dry run through `trade preview` against a sandbox would validate the execution path before any live capital is at risk.

### 11. Sharpe ratio optimisation
The current strategy targets absolute return. Sizing positions by `confidence / atr_norm` instead of a fixed cost cap would reduce drawdown without proportionally reducing returns.
