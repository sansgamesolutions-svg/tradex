# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradeX is a multi-asset (stocks, crypto, forex) trade prediction system using a hybrid ML + technical analysis approach. It supports: single-asset prediction and backtesting via CLI, batch qualification pipelines for stock/crypto universes, a one-day paper-trading simulator (Drill), live order submission via IBKR/Kraken, and a REST API.

## Environment Setup

Uses `uv` for package management and `ruff` for linting/formatting.

```bash
uv venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix
uv sync
cp .env.example .env          # fill in broker credentials and API keys
```

## Common Commands

```bash
# Predict / backtest / fetch / train (single asset)
uv run python -m tradex predict --asset BTC/USD --timeframe 1d
uv run python -m tradex backtest --asset AAPL --timeframe 1d --start 2022-01-01
uv run python -m tradex fetch --asset AAPL --timeframe 1d
uv run python -m tradex train --asset AAPL --timeframe 1d --model xgboost

# Qualification pipelines
uv run python -m tradex stocks qualify
uv run python -m tradex stocks train-approved
uv run python -m tradex crypto qualify
uv run python -m tradex crypto train-approved

# Drill (paper-trading session)
uv run python -m tradex drill prepare
uv run python -m tradex drill run
uv run python -m tradex drill report

# REST API
uv run uvicorn tradex.api.app:app --reload

# Tests
uv run pytest
uv run pytest tests/test_signals.py
uv run pytest tests/test_models.py::test_lstm_predict -v

# Lint / format
uv run ruff check .
uv run ruff format .
uv run ruff check --fix .
```

## Architecture

### CLI (`tradex/__main__.py`)

Click-based. Five command groups:
- **Core**: `predict`, `backtest`, `fetch`, `train` — single-asset workflows
- **`stocks`**: `refresh-universe`, `qualify`, `train-approved` — S&P 500 batch pipeline
- **`crypto`**: same shape — Kraken USD spot pipeline
- **`drill`**: `prepare`, `run`, `status`, `halt`, `report` — paper-trading session
- **`trade`**: single command for live order submission (preview + submit)

All subcommands lazy-import their dependencies.

### Data Flow

```
fetch(asset, tf)
  → add_indicators(df)          # EMA/MACD/RSI/BB/ATR/OBV via pandas_ta
  → build_features(df)          # drop OHLCV; returns/log_returns/HL_range/OC_range
  → make_target(df)             # binary: 1 if close[+horizon] > close
  → BaseModel.fit(X, y)         # saved to storage as {model}_{asset}_{tf}.pkl

predict time:
  BaseModel.predict_proba(X)    # float in [0, 1]
  + assess_technical(raw_df)    # TechnicalAssessment: probability + bullish/bearish_confirmed
  + gate modules (if enabled)   # trend/momentum/volume/volatility/mean_reversion/news
  → DecisionEngine.decide()     # fuses probabilities, applies thresholds + gate vetos
  → Decision(signal, fused_probability, confidence, reason, ...)
```

### Models (`tradex/models/`)

`BaseModel` (ABC in `base.py`) defines: `fit(X, y)`, `predict_probabilities(X) → np.ndarray`, `predict_proba(X) → float`, `evaluate(X, y) → dict`, `save(asset, tf)`, `load(asset, tf)`.

Registry in `__init__.py` maps name strings to classes:
- `"xgboost"` → `XGBoostModel` (sklearn-compatible wrapper)
- `"random_forest"` → `RandomForestModel`
- `"lstm"` → `LSTMModel` (PyTorch; converts DataFrames to sequences of length `settings.lookback_periods`)

All models return an upward-move probability in [0, 1]. Artifacts are serialized via joblib through the storage abstraction.

### Indicators (`tradex/indicators/`)

`technical.py` — primary: `add_indicators(df)` appends EMA(20/50/200), MACD, RSI(14), Stochastic, Bollinger(20), ATR(14), OBV. `assess_technical(df)` returns `TechnicalAssessment` with `.probability` (0–1) and `.bullish_confirmed` / `.bearish_confirmed`.

Six gate modules (each returns an Assessment with `.bullish_gate` / `.bearish_gate`):
- `trend.py` — ADX strength, trend direction, SuperTrend, higher-highs/lows
- `momentum.py` — ROC, MACD histogram slope, Stochastic crossover
- `volume.py` — volume ratio vs 20-MA, OBV slope, OBV divergence
- `volatility.py` — ATR breakout or Bollinger squeeze (configurable)
- `mean_reversion.py` — RSI oversold/overbought + Bollinger Band touch + z-score
- `sentiment.py` — VADER sentiment on Finnhub headlines; no articles → neutral pass

### Strategy (`tradex/strategy/`)

`StrategyConfig` (frozen dataclass, `schema.py`) is the single knob that controls the combiner:
- `model_weight` / `ta_weight` / `ml_ta_threshold` / `ta_only_threshold`
- `gates: GatesConfig` — toggles and parameters for each of the 6 gate modules
- `timeframes: TimeframeConfig` — primary TF + confirmation TFs + `require_alignment` flag
- `position_sizing: PositionSizingConfig` — fixed or confidence-scaled sizing

Load via `StrategyConfig.load(path)` or `StrategyConfig.default()`. Eight presets live in `config/strategies/*.json`. Pass a strategy to `SignalCombiner(strategy=cfg)` or `DrillEngine(strategy=cfg)`.

### Signal Combiner (`tradex/signals/combiner.py`)

`SignalCombiner.predict(features, raw_df) → Decision`:
1. Gets ML probability (or `None` if no trained artifact)
2. Runs `assess_technical` for TA baseline
3. Iterates enabled gates; each gate's `.bullish_gate` / `.bearish_gate` are AND-ed into running flags
4. Calls `DecisionEngine.decide()` with fused inputs and combined confirmation flags
5. Optional multi-timeframe veto (`multitf.py`): if `require_alignment=True` and higher TFs disagree, overrides to HOLD

### Decision Engine (`tradex/decision/`)

`DecisionEngine.decide()` fuses ML + TA probabilities via weighted average, compares against thresholds, then gates on `bullish_confirmed` / `bearish_confirmed`. Returns a frozen `Decision` dataclass with: `signal`, `fused_probability`, `confidence` (`|fused - 0.5| * 2`), `source` ("ML_TA" or "TA_ONLY"), `policy_version`, `confirmation_details` dict, and a human-readable `reason` string.

The TA-only path uses a stricter threshold (`ta_only_signal_threshold` in settings, default 0.65 vs 0.55 for ML+TA).

### Qualification Pipelines (`tradex/stocks/`, `tradex/crypto/`)

Both pipelines follow the same shape: eligibility check (min bars, dollar volume, class balance) → 4-fold walk-forward validation (60% initial train, 10% per fold) → approve if median ROC-AUC > 0.52 and ≥ 3 folds beat baseline. Approved symbols get a fitted model artifact saved; others are marked TA-only.

### Drill Subsystem (`tradex/drill/`)

Automated one-day paper-trading simulation:

- **`DrillEngine`** orchestrates the session lifecycle: `prepare()` runs qualification per symbol (stocks via yfinance, crypto via ccxt/Kraken), `run_live()` fires APScheduler cycles every 5 minutes between market open and close.
- **`DrillStore`** (SQLite3) is the single source of truth: drills, portfolios, signals, orders, fills, positions, prices, equity curve. Orders use idempotency keys so restarts are safe.
- **`LiveDrillMarketData`** fetches 5-minute OHLCV: Yahoo Finance for stocks, ccxt Kraken for crypto.
- **`DrillSignalService`** runs qualification + signal generation per symbol using the same `SignalCombiner` path as live prediction.

Cycle logic (every 5 min): capture quotes → fill pending orders → evaluate exits (stop-loss/take-profit) → evaluate entries (if in entry window) → expire stale signals → force-close if past deadline → record equity.

`DrillConfig` (from `types.py`) controls all session parameters: symbols, capital, position sizing, stop-loss/take-profit rates, slippage/fee models, market-hours windows.

### Execution (`tradex/execution/`)

`TradingPlatform` protocol defines: `preview(request) → OrderPreview`, `submit(request) → OrderResult`. `PlatformRegistry` selects the platform by asset type at request time — IBKR for STOCK/FOREX, Kraken for CRYPTO. Register new brokers via `registry.register(name, factory, asset_types)`.

### Storage (`tradex/storage/`)

All model artifacts and data cache go through a pluggable `Storage` backend. `get_storage()` returns `LocalStorage` (default) or `S3Storage` based on `settings.storage_backend`. Key naming conventions: `models/artifacts/{model}_{asset}_{tf}.pkl`, `data/cache/{asset}_{tf}.pkl`.

### REST API (`tradex/api/`)

FastAPI app (`app.py`) with endpoints: `POST /predict`, `POST /train`, `POST /backtest`, `GET /drill/` (dashboard router). APScheduler runs daily prediction jobs if `settings.schedule_assets` is set. Start with `uvicorn tradex.api.app:app`.

### Configuration

`tradex/config/settings.py` — `Settings` dataclass loaded from (in priority order): `TRADEX_*` environment variables → `config.yaml` in project root → hardcoded defaults. Key fields: `default_timeframe`, `lookback_periods` (60), `prediction_horizon` (1), `signal_threshold` (0.55), `ta_only_signal_threshold` (0.65), `model_weight` (0.6), `ta_weight` (0.4), storage backend, drill session parameters, broker credentials.

### Key Design Decisions

- **TA-only fallback**: when no trained ML model exists, `SignalCombiner` uses TA-only mode with a stricter threshold — no code path change needed in callers.
- **Gate AND logic**: all enabled gates must pass for the direction; any single gate can veto a BUY or SELL to HOLD. Gates are evaluated in order: trend → momentum → volume → volatility → mean_reversion → news.
- **Time-series safety**: all train/test splits are positional (no shuffle); qualification uses walk-forward folds; drill preparation excludes the drill date from training data.
- **Idempotent drill orders**: `DrillStore.create_order()` takes an idempotency key; repeated calls with the same key are no-ops.
- **Frozen dataclasses throughout**: `Decision`, `DrillConfig`, `PriceQuote`, `OrderRequest`, all gate configs — immutable after construction.
- **Lazy CLI imports**: each Click subcommand imports its subsystem only when executed, keeping startup fast.
