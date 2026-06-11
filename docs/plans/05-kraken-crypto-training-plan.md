# Kraken Crypto Training Pipeline Plan

**Status:** Implemented

## Objective

Extend the qualification and approved-training workflow to Kraken USD spot
markets while preserving the shared model evaluation and artifact interfaces.

## Delivered Work

1. Add a versioned Kraken USD spot-market snapshot with retrieval metadata.
2. Fetch public market metadata and daily OHLCV data without API credentials.
3. Exclude inactive markets and non-spot products.
4. Exclude stablecoins, wrapped assets, and commodity-pegged assets by default.
5. Add crypto-specific universe refresh, qualification, and approved-training
   commands.
6. Reuse chronological walk-forward evaluation and common report structures.
7. Save trained artifacts only for approved crypto symbols.
8. Continue qualification and training after per-symbol failures.

## Eligibility Defaults

Crypto thresholds are configured separately from stock thresholds because
markets trade continuously and have different history and liquidity profiles.
The checks cover:

- Minimum completed daily bars and post-feature samples.
- Minimum latest USD close.
- Minimum rolling median USD notional volume.
- Duplicate and non-finite bars.
- Missing daily sessions relative to the continuous crypto calendar.
- Maximum current-bar staleness.
- Minimum minority target-class representation.

## Approval Rules

The pipeline uses four expanding chronological folds and records ROC-AUC,
balanced accuracy, and majority-class baseline accuracy for every fold. Approval
uses configurable median metric thresholds and a minimum count of folds that
beat the majority baseline.

## Interfaces

- `tradex crypto refresh-universe`
- `tradex crypto qualify --model <model>`
- `tradex crypto train-approved --report <report>`
- Kraken market snapshot and metadata types
- Shared eligibility, fold metric, and qualification report types
- Daily timeframe only for the first version

## Validation

- Test deterministic market filtering and snapshot serialization.
- Test Kraken symbol normalization and public OHLCV parsing.
- Test stablecoin, wrapped-token, commodity-peg, inactive, and non-spot
  exclusions.
- Test crypto eligibility failures and threshold boundaries.
- Test chronological folds and approval decisions.
- Test report round-trips and approved-only artifact creation.
- Test failure isolation during batch qualification and training.

## Extension Boundary

Additional quote currencies and exchanges should use provider-specific universe
and data adapters while reusing the qualification engine. Intraday timeframes,
derivatives, on-chain features, and profitability gates remain follow-up work.
