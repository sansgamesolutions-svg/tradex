# One-Day Automated Trading Drill

TradeX can run a one-session simulation using real public prices and completely
internal execution. It does not read IBKR or Kraken credentials and cannot send
an order to either platform.

## June 12, 2026 Runbook

Prepare the fixed watchlists before `9:20 a.m. ET`:

```powershell
uv run python -m tradex drill prepare --date 2026-06-12
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

The scheduler evaluates entries once at `9:35 a.m.`, monitors prices and exits
every five minutes, stops new entries at `3:50 p.m.`, closes remaining positions
at `3:55 p.m.`, and writes reports after `4:00 p.m. ET`.

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
- New-entry halt after three consecutive quote-failure cycles
- Entry rejection for prices more than ten minutes stale

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
