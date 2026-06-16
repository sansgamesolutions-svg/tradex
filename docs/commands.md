# TradeX Command Reference

All commands use `uv run python -m tradex`. Run any command with `--help` to see all options.

---

## Environment Setup

```powershell
# Create virtual environment
uv venv

# Activate (Windows)
.venv\Scripts\activate

# Install all dependencies
uv sync

# Copy and fill in credentials
cp .env.example .env
```

---

## Development Commands

```powershell
# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_models.py

# Run a single test by name
uv run pytest tests/test_models.py::test_lstm_predict -v

# Lint
uv run ruff check .

# Format
uv run ruff format .

# Auto-fix lint issues
uv run ruff check --fix .
```

---

## Core Commands

### `fetch` — Download and cache market data

```powershell
# Fetch latest daily data for a stock
uv run python -m tradex fetch --asset AAPL

# Fetch crypto on a 1-hour timeframe
uv run python -m tradex fetch --asset BTC/USD --timeframe 1h

# Fetch with a specific date range
uv run python -m tradex fetch --asset AAPL --start 2023-01-01 --end 2024-01-01

# Fetch forex
uv run python -m tradex fetch --asset EUR/USD --timeframe 4h
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--asset` | *(required)* | Symbol, e.g. `AAPL`, `BTC/USD`, `EUR/USD` |
| `--timeframe` | `1d` | `1m` `5m` `15m` `1h` `4h` `1d` `1w` |
| `--start` | *(earliest available)* | Start date `YYYY-MM-DD` |
| `--end` | *(today)* | End date `YYYY-MM-DD` |

---

### `train` — Train a model and save artifact

```powershell
# Train XGBoost on AAPL daily
uv run python -m tradex train --asset AAPL --model xgboost

# Train Random Forest on BTC/USD hourly
uv run python -m tradex train --asset BTC/USD --timeframe 1h --model random_forest

# Train LSTM on AAPL with a date range
uv run python -m tradex train --asset AAPL `
  --model lstm `
  --start 2020-01-01 `
  --end 2024-01-01
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--asset` | *(required)* | Asset symbol |
| `--timeframe` | `1d` | Candle timeframe |
| `--model` | `xgboost` | `xgboost` `random_forest` `lstm` |
| `--start` | *(auto)* | Training data start date |
| `--end` | *(today)* | Training data end date |

---

### `predict` — Generate a BUY / SELL / HOLD signal

```powershell
# Predict next-day direction for AAPL
uv run python -m tradex predict --asset AAPL

# Predict using a specific model
uv run python -m tradex predict --asset BTC/USD --model random_forest

# Predict on hourly timeframe
uv run python -m tradex predict --asset EUR/USD --timeframe 1h --model xgboost
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--asset` | *(required)* | Asset symbol |
| `--timeframe` | `1d` | Candle timeframe |
| `--model` | `xgboost` | `xgboost` `random_forest` `lstm` |

---

### `backtest` — Run a historical simulation

```powershell
# Backtest AAPL from 2022
uv run python -m tradex backtest --asset AAPL --start 2022-01-01

# Backtest BTC/USD over a specific window with Random Forest
uv run python -m tradex backtest --asset BTC/USD `
  --start 2021-01-01 `
  --end 2023-12-31 `
  --model random_forest

# Backtest on hourly bars
uv run python -m tradex backtest --asset AAPL --timeframe 1h --start 2023-01-01
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--asset` | *(required)* | Asset symbol |
| `--timeframe` | `1d` | Candle timeframe |
| `--start` | *(required)* | Start date `YYYY-MM-DD` |
| `--end` | *(today)* | End date `YYYY-MM-DD` |
| `--model` | `xgboost` | `xgboost` `random_forest` `lstm` |

---

## Stocks Pipeline

### Step 1 — Refresh the S&P 500 universe snapshot

```powershell
# Update constituent list from Wikipedia (run before qualify)
uv run python -m tradex stocks refresh-universe

# Save snapshot to a custom path
uv run python -m tradex stocks refresh-universe --output reports/sp500-snapshot.json
```

### Step 2 — Qualify stocks with walk-forward validation

```powershell
# Qualify all S&P 500 stocks (writes reports/stock-qualification-*.json + .csv)
uv run python -m tradex stocks qualify

# Qualify with a specific model
uv run python -m tradex stocks qualify --model random_forest

# Qualify with a custom universe snapshot
uv run python -m tradex stocks qualify --universe reports/sp500-snapshot.json

# Qualify with a training history start date
uv run python -m tradex stocks qualify --start 2018-01-01

# Qualify and write report to a specific path
uv run python -m tradex stocks qualify --report reports/my-run.json
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--model` | `xgboost` | `xgboost` `random_forest` `lstm` |
| `--report` | `reports/stock-qualification-<timestamp>.json` | Output JSON path |
| `--universe` | *(packaged snapshot)* | Universe snapshot path |
| `--start` | *(auto)* | Training history start date |

### Step 3 — Train final artifacts for approved stocks

```powershell
# Train all approved stocks from a qualification report
uv run python -m tradex stocks train-approved `
  --report reports/stock-qualification-20260611T120000Z.json
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--report` | *(required)* | Path to qualification JSON report |

---

## Crypto Pipeline

### Step 1 — Refresh the Kraken USD spot universe

```powershell
# Update market list from Kraken public API
uv run python -m tradex crypto refresh-universe

# Save snapshot to a custom path
uv run python -m tradex crypto refresh-universe --output reports/kraken-snapshot.json
```

### Step 2 — Qualify crypto markets

```powershell
# Qualify all Kraken USD spot markets
uv run python -m tradex crypto qualify

# Qualify with Random Forest
uv run python -m tradex crypto qualify --model random_forest

# Qualify with a custom universe snapshot
uv run python -m tradex crypto qualify --universe reports/kraken-snapshot.json

# Write report to a custom path
uv run python -m tradex crypto qualify --report reports/crypto-run.json
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--model` | `xgboost` | `xgboost` `random_forest` |
| `--report` | `reports/crypto-qualification-<timestamp>.json` | Output JSON path |
| `--universe` | *(packaged snapshot)* | Universe snapshot path |

### Step 3 — Train final artifacts for approved crypto markets

```powershell
# Train all approved crypto markets from a qualification report
uv run python -m tradex crypto train-approved `
  --report reports/crypto-qualification-20260611T120000Z.json
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--report` | *(required)* | Path to qualification JSON report |

---

## Automated Paper Trading Drill

The drill runs a full isolated paper-trading session without placing real broker orders.

### Step 1 — Prepare (fetch data and train session models)

```powershell
# Prepare a drill for today's session
uv run python -m tradex drill prepare --date 2026-06-11
```

### Step 2 — Run the live scheduler

```powershell
# Run the blocking 5-minute cycle scheduler for the full session
uv run python -m tradex drill run --date 2026-06-11
```

The scheduler executes cycles every 5 minutes from market open through close, then exits automatically.

### Monitor status during a running drill

```powershell
# Print the latest drill state (portfolios, positions, signals, orders)
uv run python -m tradex drill status
```

### Generate a report after the session

```powershell
# Write JSON report (default)
uv run python -m tradex drill report

# Write HTML report
uv run python -m tradex drill report --format html

# Write to a specific path
uv run python -m tradex drill report --format json --output reports/drill-2026-06-11.json
```

### Emergency halt

```powershell
# Halt the running drill (interactive confirmation)
uv run python -m tradex drill halt

# Halt without confirmation prompt
uv run python -m tradex drill halt --yes
```

**Drill configuration** (via `.env` or environment variables):

| Variable | Default | Description |
|---|---|---|
| `TRADEX_DRILL_INITIAL_CAPITAL` | `5000` | Starting capital ($) |
| `TRADEX_DRILL_MAX_POSITION_COST` | `500` | Max cost per position ($) |
| `TRADEX_DRILL_MAX_OPEN_POSITIONS` | `2` | Max simultaneous positions |
| `TRADEX_DRILL_STOP_LOSS_RATE` | `0.01` | Stop-loss (1% of entry) |
| `TRADEX_DRILL_TAKE_PROFIT_RATE` | `0.02` | Take-profit (2% of entry) |
| `TRADEX_DRILL_MAX_DRAWDOWN_RATE` | `0.01` | Drawdown limit before halt |

---

## Trade (Live Order Execution)

> Requires IBKR TWS / Gateway running (stocks/forex) or Kraken API keys (crypto).  
> Omit `--submit` to preview the order without sending it.

```powershell
# Preview a market buy of 10 AAPL shares on IBKR
uv run python -m tradex trade --side BUY --asset AAPL --quantity 10

# Submit the order
uv run python -m tradex trade --side BUY --asset AAPL --quantity 10 --submit

# Limit sell 5 AAPL at $200
uv run python -m tradex trade `
  --side SELL `
  --asset AAPL `
  --quantity 5 `
  --order-type LIMIT `
  --limit-price 200 `
  --submit

# Buy 0.01 BTC via Kraken
uv run python -m tradex trade `
  --side BUY `
  --asset BTC `
  --quantity 0.01 `
  --asset-type CRYPTO `
  --submit

# Forex: buy 10000 EUR/USD via IBKR (GTC)
uv run python -m tradex trade `
  --side BUY `
  --asset EUR/USD `
  --quantity 10000 `
  --asset-type FOREX `
  --time-in-force GTC `
  --submit

# Force a specific platform
uv run python -m tradex trade --side BUY --asset AAPL --quantity 1 --platform ibkr --submit
```

**Options:**

| Flag | Default | Description |
|---|---|---|
| `--side` | *(required)* | `BUY` or `SELL` |
| `--asset` | *(required)* | Symbol: `AAPL`, `BTC`, `EUR/USD` |
| `--quantity` | *(required)* | Number of shares / coins / units |
| `--asset-type` | `STOCK` | `STOCK` `FOREX` `CRYPTO` |
| `--order-type` | `MARKET` | `MARKET` `LIMIT` |
| `--limit-price` | *(none)* | Required when `--order-type LIMIT` |
| `--exchange` | *(auto)* | IBKR exchange override |
| `--currency` | `USD` | Settlement currency |
| `--time-in-force` | `DAY` | `DAY` `GTC` |
| `--outside-rth` | `false` | Allow execution outside regular hours |
| `--platform` | *(auto-detected)* | `ibkr` or `kraken` |
| `--submit` | `false` | Transmit order (preview-only without this flag) |

---

## REST API Server

```powershell
# Start the API server (default: http://127.0.0.1:8000)
uv run uvicorn tradex.api.app:app --reload

# Bind to a specific host/port
uv run uvicorn tradex.api.app:app --host 0.0.0.0 --port 8080

# Production (no reload)
uv run uvicorn tradex.api.app:app --host 0.0.0.0 --port 8000 --workers 2
```

**Key endpoints:**

| Method | Path | Description |
|---|---|---|
| `POST` | `/predict` | Generate a BUY/SELL/HOLD signal |
| `POST` | `/train` | Train a model artifact |
| `POST` | `/backtest` | Run a historical backtest |
| `GET` | `/drill/` | Drill dashboard (latest session status) |
| `GET` | `/docs` | Interactive Swagger UI |

---

## Storage Configuration

```powershell
# Use local filesystem (default — no config needed)
# Artifacts: models/artifacts/   Cache: data/cache/

# Switch to S3 (set in .env)
$env:TRADEX_STORAGE_BACKEND = "s3"
$env:TRADEX_S3_BUCKET        = "my-tradex-bucket"
$env:AWS_ACCESS_KEY_ID       = "AKIA..."
$env:AWS_SECRET_ACCESS_KEY   = "..."

# Use MinIO instead of AWS S3
$env:TRADEX_S3_ENDPOINT_URL  = "http://localhost:9000"
```

---

## Typical End-to-End Workflow

```powershell
# 1. Fetch and cache data
uv run python -m tradex fetch --asset AAPL --start 2020-01-01

# 2. Train a model
uv run python -m tradex train --asset AAPL --model xgboost

# 3. Get a prediction
uv run python -m tradex predict --asset AAPL

# 4. Backtest the strategy
uv run python -m tradex backtest --asset AAPL --start 2022-01-01

# 5. (Optional) Submit a live trade
uv run python -m tradex trade --side BUY --asset AAPL --quantity 10 --submit
```

```powershell
# Full stock pipeline (screen → qualify → train → predict)
uv run python -m tradex stocks refresh-universe
uv run python -m tradex stocks qualify --model xgboost
uv run python -m tradex stocks train-approved `
  --report reports/stock-qualification-20260611T120000Z.json
uv run python -m tradex predict --asset AAPL
```

```powershell
# Full crypto pipeline
uv run python -m tradex crypto refresh-universe
uv run python -m tradex crypto qualify --model xgboost
uv run python -m tradex crypto train-approved `
  --report reports/crypto-qualification-20260611T120000Z.json
uv run python -m tradex predict --asset BTC/USD
```

```powershell
# Full drill session for today
uv run python -m tradex drill prepare --date 2026-06-11
uv run python -m tradex drill run    --date 2026-06-11
uv run python -m tradex drill report --format html
```
