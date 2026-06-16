from __future__ import annotations

import json
import time
from datetime import datetime, timedelta, timezone

from tradex.storage import get_storage

try:
    import finnhub
    _FINNHUB_AVAILABLE = True
except ImportError:
    _FINNHUB_AVAILABLE = False


def _cache_key(symbol: str, lookback_hours: int) -> str:
    bucket = datetime.now(tz=timezone.utc).strftime("%Y%m%d_%H")
    return f"news/cache/{symbol.replace('/', '_')}_{lookback_hours}h_{bucket}.json"


def fetch_news(symbol: str, api_key: str, lookback_hours: int = 24) -> list[str]:
    """Return list of headline strings for the symbol from Finnhub, with TTL cache."""
    cache_key = _cache_key(symbol, lookback_hours)
    storage = get_storage()

    cached = storage.get(cache_key)
    if cached is not None:
        return json.loads(cached.decode())

    if not _FINNHUB_AVAILABLE or not api_key:
        return []

    client = finnhub.Client(api_key=api_key)
    to_dt = datetime.now(tz=timezone.utc)
    from_dt = to_dt - timedelta(hours=lookback_hours)
    from_str = from_dt.strftime("%Y-%m-%d")
    to_str = to_dt.strftime("%Y-%m-%d")

    # Finnhub uses stock tickers; crypto symbols like BTC/USD → BINANCE:BTCUSDT not supported here.
    # Callers should pass the Finnhub-compatible ticker (e.g. "AAPL").
    try:
        news = client.company_news(symbol, _from=from_str, to=to_str)
    except Exception:
        return []

    headlines = [item.get("headline", "") for item in news if item.get("headline")]

    storage.put(cache_key, json.dumps(headlines).encode())
    return headlines
