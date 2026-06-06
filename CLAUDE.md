# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Project Overview

TradeX is a multi-asset (stocks, crypto, forex) trade prediction application using a hybrid approach: ML/deep learning models combined with technical analysis signals, exposed via CLI and Python scripts.

## Environment Setup

This project uses `uv` for package and environment management, and `ruff` for linting/formatting.

```bash
# Create and activate virtual environment
uv venv
.venv\Scripts\activate        # Windows
source .venv/bin/activate     # Unix

# Install dependencies
uv sync

# Add a new dependency
uv add <package>
uv add --dev <package>        # dev/test dependency
```

## Common Commands

```bash
# Run predictions
uv run python -m tradex predict --asset BTC --timeframe 1d

# Run all tests
uv run pytest

# Run a single test file
uv run pytest tests/test_models.py

# Run a single test by name
uv run pytest tests/test_models.py::test_lstm_predict -v

# Lint and format
uv run ruff check .
uv run ruff format .
uv run ruff check --fix .     # auto-fix lint issues
```

## Architecture

```
tradex/
├── __main__.py          # CLI entry point (argparse or click)
├── data/
│   ├── fetcher.py       # Market data ingestion (yfinance, ccxt, etc.)
│   ├── preprocessor.py  # Normalization, feature engineering, train/test splits
│   └── cache.py         # Local data caching layer
├── indicators/
│   └── technical.py     # TA signals: RSI, MACD, Bollinger Bands, ATR, etc.
├── models/
│   ├── base.py          # Abstract BaseModel interface (fit, predict, evaluate)
│   ├── ml/              # scikit-learn models (RandomForest, XGBoost, etc.)
│   └── dl/              # Deep learning models (LSTM, Transformer)
├── signals/
│   └── combiner.py      # Fuses ML output + TA signals into a final signal
├── backtester/
│   └── engine.py        # Walk-forward backtesting, performance metrics
└── config/
    └── settings.py      # Centralized config (asset lists, hyperparams, paths)

tests/
├── test_data.py
├── test_indicators.py
├── test_models.py
└── test_signals.py
```

### Data Flow

```
Data Fetcher → Preprocessor → [Technical Indicators + ML Models] → Signal Combiner → CLI Output / Backtest
```

1. **Data layer** (`tradex/data/`) fetches OHLCV data per asset/timeframe and caches locally.
2. **Indicators** (`tradex/indicators/`) compute TA features from raw OHLCV; these are inputs to models and direct signal sources.
3. **Models** (`tradex/models/`) follow the `BaseModel` interface so ML and DL models are interchangeable.
4. **Signal combiner** (`tradex/signals/`) weights and merges raw model probability outputs with TA-derived signals into a single directional prediction (BUY / SELL / HOLD).
5. **Backtester** (`tradex/backtester/`) runs historical simulations using the combiner output to evaluate strategy performance.
6. **CLI** (`tradex/__main__.py`) wires all layers together and exposes subcommands: `predict`, `backtest`, `fetch`, `train`.

### Key Design Decisions

- All models implement `tradex/models/base.py::BaseModel` so they can be swapped without changing calling code.
- Asset class differences (tick size, trading hours, data sources) are abstracted in the fetcher; upstream code is asset-agnostic.
- Config is centralized in `tradex/config/settings.py` and can be overridden via environment variables or a `config.yaml` in the project root.
- Cached data lives in `data/cache/` (gitignored); trained model artifacts live in `models/artifacts/` (gitignored).
