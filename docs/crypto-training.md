# Kraken Crypto Training

TradeX qualifies one daily model per active Kraken USD spot market. The
versioned universe excludes stablecoins, fiat pairs, wrapped assets, leveraged
token patterns, inactive markets, and non-spot products.

Refresh the Kraken market snapshot:

```powershell
uv run python -m tradex crypto refresh-universe
```

Qualify all markets using public daily OHLCV data:

```powershell
uv run python -m tradex crypto qualify --model xgboost
```

Train final artifacts from an approved JSON report:

```powershell
uv run python -m tradex crypto train-approved `
  --report reports/crypto-qualification-YYYYMMDDTHHMMSSZ.json
```

The default qualification thresholds reflect Kraken's public OHLC endpoint,
which provides at most 720 recent candles:

- At least 700 completed daily bars and 500 model-ready samples
- Median 90-day USD volume of at least $1 million
- At most 1% missing calendar days and at most two stale days
- At least 35% representation for the minority target class
- Median walk-forward ROC-AUC of 0.52 and balanced accuracy of 0.51
- At least three of four folds beating the training-set majority baseline

Qualification uses public market data and does not require Kraken API
credentials. Trading still requires credentials with trade permission and no
withdrawal permission.
