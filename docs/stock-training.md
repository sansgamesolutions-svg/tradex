# S&P 500 Stock Training

TradeX uses a versioned S&P 500 snapshot so qualification runs are reproducible.
Refresh it explicitly when the constituent list should change:

```powershell
uv run python -m tradex stocks refresh-universe
```

Qualify every constituent with daily data and four expanding walk-forward folds:

```powershell
uv run python -m tradex stocks qualify --model xgboost
```

The command writes a canonical JSON report and a CSV summary under `reports/`.
The JSON contains the universe retrieval date, thresholds, data-quality results,
rejection reasons, and per-fold metrics.

Train final per-stock artifacts from an approved report:

```powershell
uv run python -m tradex stocks train-approved `
  --report reports/stock-qualification-YYYYMMDDTHHMMSSZ.json
```

Qualification requires, by default:

- 1,250 completed daily bars and 1,000 model-ready feature rows
- Latest adjusted close of at least $5
- Median 252-session dollar volume of at least $25 million
- At most 1% missing SPY sessions and at most three stale sessions
- At least 35% representation for the minority target class
- Median walk-forward ROC-AUC of 0.52 and balanced accuracy of 0.51
- At least three of four folds beating the training-set majority baseline

Thresholds can be overridden in `config.yaml` or through matching `TRADEX_*`
environment variables. Qualification measures predictive reliability; it does
not yet apply a profitability-after-costs deployment gate.
