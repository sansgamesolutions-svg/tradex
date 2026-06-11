# S&P 500 Training Pipeline Plan

**Status:** Implemented

## Objective

Build a reproducible daily-model pipeline that screens current S&P 500 stocks,
measures data and model quality, and trains artifacts only for approved symbols.

## Delivered Work

1. Store a versioned S&P 500 constituent snapshot with retrieval metadata.
2. Add `tradex stocks refresh-universe` using the public Wikipedia table.
3. Normalize constituent symbols for Yahoo Finance compatibility.
4. Remove rows with unavailable future targets instead of labeling them down.
5. Add `tradex stocks qualify --model xgboost`.
6. Evaluate eligible symbols with four expanding walk-forward folds.
7. Save canonical JSON reports and review-friendly CSV reports.
8. Add `tradex stocks train-approved --report <report>`.
9. Continue batch training after an individual symbol failure.

## Eligibility Defaults

- At least 1,250 completed daily bars.
- At least 1,000 samples after feature generation.
- Latest adjusted close of at least `$5`.
- Median adjusted close times volume of at least `$25M` over 252 sessions.
- No duplicate or non-finite bars.
- No more than 1% missing sessions relative to SPY.
- Latest bar no more than three sessions stale.
- Minority target class of at least 35%.

## Approval Defaults

- Four chronological expanding folds with no future leakage.
- Median ROC-AUC of at least `0.52`.
- Median balanced accuracy of at least `0.51`.
- At least three folds beat their majority-class accuracy baseline.

## Interfaces

- `tradex stocks refresh-universe`
- `tradex stocks qualify --model <model>`
- `tradex stocks train-approved --report <report>`
- Stock universe, eligibility result, fold metrics, and qualification report
  types
- Daily timeframe only for the first version

## Validation

- Test deterministic snapshot parsing and ticker normalization.
- Test every eligibility rejection reason and threshold boundary.
- Test target alignment removes the final prediction-horizon rows.
- Test chronological folds and absence of future leakage.
- Test approval thresholds and majority-baseline comparisons.
- Test that only approved symbols produce artifacts.
- Test that batch processing records failures and continues.

## Extension Boundary

Historical index membership and survivorship-bias correction are outside this
plan. Qualification measures predictive reliability, not trading profitability;
transaction-cost and strategy-return gates can be added later.
