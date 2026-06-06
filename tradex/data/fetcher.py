from __future__ import annotations

import pandas as pd
import yfinance as yf

from tradex.data import cache

_TF_MAP: dict[str, str] = {
    "1m": "1m",
    "5m": "5m",
    "15m": "15m",
    "1h": "60m",
    "4h": "240m",
    "1d": "1d",
    "1w": "1wk",
}

_CRYPTO_BASE = {"BTC", "ETH", "SOL", "XRP", "BNB", "ADA", "DOGE", "AVAX", "DOT", "MATIC"}


def _yf_symbol(asset: str) -> str:
    upper = asset.upper().replace("/", "")
    if upper.rstrip("USD") in _CRYPTO_BASE or upper.endswith("USD") and "-" not in asset:
        base = upper.rstrip("USD")
        return f"{base}-USD"
    return asset.upper()


def _cache_covers(cached: pd.DataFrame, start: str | None) -> bool:
    """Return True if cached data already covers the requested start date."""
    if start is None:
        return True
    if cached.empty:
        return False
    return cached.index[0].date() <= pd.Timestamp(start).date()


def fetch(
    asset: str,
    timeframe: str = "1d",
    start: str | None = None,
    end: str | None = None,
    force_refresh: bool = False,
) -> pd.DataFrame:
    """Return OHLCV DataFrame for *asset* at *timeframe* granularity.

    Data is cached locally as pickle. The cache is bypassed when the requested
    start date predates what is already cached.
    """
    if not force_refresh:
        cached = cache.load(asset, timeframe)
        if cached is not None and _cache_covers(cached, start):
            if end is None:
                return cached
            # Slice to requested end date if provided
            end_ts = pd.Timestamp(end, tz="UTC")
            return cached[cached.index <= end_ts]

    symbol = _yf_symbol(asset)
    interval = _TF_MAP.get(timeframe, "1d")

    ticker = yf.Ticker(symbol)
    df: pd.DataFrame = ticker.history(start=start, end=end, interval=interval, auto_adjust=True)

    if df.empty:
        raise ValueError(
            f"No data returned for '{asset}' ({timeframe}). Check the symbol and timeframe."
        )

    df.index = pd.to_datetime(df.index, utc=True)
    df.columns = [c.lower() for c in df.columns]
    df = df[["open", "high", "low", "close", "volume"]].dropna()

    cache.save(asset, timeframe, df)
    return df
