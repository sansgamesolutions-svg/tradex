from __future__ import annotations

from datetime import UTC, datetime
from typing import Any, Protocol

import ccxt
import pandas as pd

from tradex.config.settings import settings


class OHLCVClient(Protocol):
    def load_markets(self) -> dict[str, Any]: ...

    def fetch_ohlcv(
        self,
        symbol: str,
        timeframe: str = "1d",
        since: int | None = None,
        limit: int | None = None,
    ) -> list[list[float]]: ...


class KrakenMarketData:
    """Public Kraken spot market-data client for daily model training."""

    def __init__(self, client: OHLCVClient | None = None) -> None:
        self._owns_client = client is None
        self.client = client or ccxt.kraken(
            {
                "enableRateLimit": True,
                "timeout": int(settings.kraken_timeout),
                "options": {"defaultType": "spot"},
            }
        )
        self._markets_loaded = False

    def fetch_daily(
        self,
        symbol: str,
        *,
        limit: int = 720,
        now: datetime | None = None,
    ) -> pd.DataFrame:
        if not self._markets_loaded:
            self.client.load_markets()
            self._markets_loaded = True
        rows = self.client.fetch_ohlcv(symbol, timeframe="1d", limit=limit)
        if not rows:
            raise ValueError(f"No Kraken OHLCV data returned for {symbol}")

        frame = pd.DataFrame(
            rows,
            columns=("timestamp", "open", "high", "low", "close", "volume"),
        )
        frame.index = pd.to_datetime(frame.pop("timestamp"), unit="ms", utc=True)
        frame = frame.astype(float)
        current_date = (now or datetime.now(UTC)).date()
        return frame[frame.index.date < current_date]

    def close(self) -> None:
        if self._owns_client:
            close = getattr(self.client, "close", None)
            if callable(close):
                close()
