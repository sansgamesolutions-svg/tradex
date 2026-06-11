# One-Day Automated Trading Drill Plan

**Status:** Implemented

## Objective

Run a restart-safe, one-session stock and crypto paper drill using public market
data, isolated `$5,000` ledgers, and no connection to live broker execution.

## Delivered Work

1. Add a SQLite-backed drill state store for portfolios, prices, model
   preparation, signals, orders, fills, positions, events, and equity points.
2. Add an internal simulated broker satisfying the common platform contract.
3. Prepare XGBoost models in a drill-only artifact namespace and retain explicit
   TA-only fallback when validation fails.
4. Fetch five-minute Yahoo stock prices and public Kraken crypto prices.
5. Enforce `$500` all-in entries, two-position limits, stops, targets, stale-data
   checks, drawdown halts, and no re-entry.
6. Add a deterministic five-minute session scheduler and restart-safe
   idempotency keys.
7. Add CLI lifecycle commands, JSON/HTML reports, FastAPI status and halt
   endpoints, and a localhost dashboard.

## Safety Boundaries

- The drill never creates an IBKR or authenticated Kraken client.
- Five and ten percent returns are dashboard benchmarks, not risk targets.
- Every signal, rejection, quote timestamp, cost, and simulated fill is
  persisted for review.
- Empty or stale signals do not force trades.
- All remaining positions are submitted for simulated closure at `3:55 p.m. ET`.

## Validation

- Test isolated ledgers and cost-aware sizing.
- Test stale data, no-signal behavior, position limits, insufficient cash, stop
  loss, take profit, and session close.
- Test order idempotency and restart-safe state.
- Test report generation, dashboard state, and confirmed emergency halt.
- Run a public live-data smoke test without constructing real broker adapters.

## Extension Boundary

The drill is intentionally daily-signal and long-only. Multi-session analytics,
intraday models, passive limit simulation, secondary quote providers, and real
broker paper adapters are follow-up work after at least 20 observed sessions.
