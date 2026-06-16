# One-Day Automated Trading Drill

TradeX can run a one-session simulation using real public prices and completely
internal execution. It does not read IBKR or Kraken credentials and cannot send
an order to either platform.

The drill now runs as the `one-day-drill` profile of the reusable automatic
trading system. See `docs/automatic-trading.md` for the generic `tradex auto`
commands and FastAPI endpoints.

## June 12, 2026 Runbook

Prepare the fixed watchlists before `9:20 a.m. ET`:

```powershell
uv run python -m tradex drill prepare --date 2026-06-12
uv run python -m tradex drill prepare --date 2026-06-12 --force
```

Start the blocking session scheduler before the `9:30 a.m. ET` open:

```powershell
uv run python -m tradex drill run --date 2026-06-12
```

In another terminal, launch the dashboard on localhost:

```powershell
uv run uvicorn tradex.api.app:app --host 127.0.0.1 --port 8000
```

Open `http://127.0.0.1:8000/drill`.

The scheduler begins entry evaluation at `9:35 a.m.`, retries only unresolved
symbols every five minutes through `10:00 a.m.`, monitors prices and exits every
five minutes, stops new entries at `3:50 p.m.`, closes remaining positions at
`3:55 p.m.`, and writes reports after `4:00 p.m. ET`.

`--force` safely refreshes an existing preparation and is refused after any
simulated fill has been recorded.

## Other Commands

```powershell
uv run python -m tradex drill status
uv run python -m tradex drill halt
uv run python -m tradex drill report --format json
uv run python -m tradex drill report --format html
```

Runtime state is stored under `data/drill/`, which is ignored by Git. The
SQLite database is the source of truth after a restart.

## Default Risk Rules

- Separate `$5,000` stock and crypto portfolios
- At most `$500` including fees and adverse slippage per entry
- At most two open positions per portfolio
- Long-only with no leverage and no re-entry
- 1% stop loss and 2% take profit
- New-entry halt at a 1% portfolio drawdown
- Per-symbol disablement after three consecutive quote failures
- Portfolio entry halt after quote coverage stays below 60% for three cycles
- Entry rejection for prices more than ten minutes stale

TA-only fallback uses policy version `2.0` and requires EMA20 above EMA50, a
positive MACD histogram, RSI below 70, and TA probability of at least `0.65`.
Bearish reports use the symmetric confirmation policy. ML+TA decisions retain
the `0.55` fused threshold.

Orders cannot fill from the bar used to create them. A 9:35 order can first
fill from the completed bar ending at 9:40. This rule also applies to stop,
target, and session-close orders.

Stock simulation uses two basis points of adverse slippage and `$0.35` per
order. Crypto uses five basis points of adverse slippage and a 0.40% taker fee.

## Reading the Results

The JSON and HTML reports separate stocks, crypto, and combined performance.
They include net and cost-free returns, drawdown, fees, slippage, win rate,
capital exposure, rejected entries, data issues, and recommendations.

One day is an operational drill, not enough evidence to optimize model
thresholds. Collect at least 20 sessions before making statistically driven
changes. Useful early improvements are a secondary quote provider, passive
limit-fill simulation, correlation-aware position limits, and longer paper
observation.
