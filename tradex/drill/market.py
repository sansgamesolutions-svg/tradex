from __future__ import annotations

from datetime import UTC, date, datetime
from typing import Any, Protocol

import ccxt
import pandas as pd
import yfinance as yf

from tradex.config.settings import settings
from tradex.crypto.data import KrakenMarketData
from tradex.data.fetcher import fetch
from tradex.drill.types import PortfolioKind, PriceQuote


class DrillMarketData(Protocol):
    def fetch_daily(
        self,
        portfolio: PortfolioKind,
        symbol: str,
        cutoff: date,
    ) -> pd.DataFrame: ...

    def fetch_quote(
        self,
        portfolio: PortfolioKind,
        symbol: str,
        captured_at: datetime,
    ) -> PriceQuote: ...

    def close(self) -> None: ...


class LiveDrillMarketData:
    """Read-only Yahoo and Kraken data access for the internal simulator."""

    def __init__(self, kraken_client: Any | None = None) -> None:
        self._owns_kraken = kraken_client is None
        self.kraken = kraken_client or ccxt.kraken(
            {
                "enableRateLimit": True,
                "timeout": int(settings.kraken_timeout),
                "options": {"defaultType": "spot"},
            }
        )
        self._kraken_loaded = False

    def fetch_daily(
        self,
        portfolio: PortfolioKind,
        symbol: str,
        cutoff: date,
    ) -> pd.DataFrame:
        if portfolio == "STOCK":
            start = date(cutoff.year - 10, cutoff.month, min(cutoff.day, 28)).isoformat()
            frame = fetch(
                symbol,
                "1d",
                start=start,
                end=cutoff.isoformat(),
                force_refresh=True,
            )
            return frame[frame.index.date < cutoff]

        client = KrakenMarketData(client=self.kraken)
        frame = client.fetch_daily(
            symbol,
            limit=720,
            now=datetime.combine(cutoff, datetime.min.time(), tzinfo=UTC),
        )
        return frame[frame.index.date < cutoff]

    def fetch_quote(
        self,
        portfolio: PortfolioKind,
        symbol: str,
        captured_at: datetime,
    ) -> PriceQuote:
        if portfolio == "STOCK":
            frame = yf.Ticker(symbol).history(
                period="1d",
                interval="5m",
                auto_adjust=True,
                prepost=False,
            )
            if frame.empty:
                raise ValueError(f"No five-minute Yahoo quote returned for {symbol}")
            source_timestamp = pd.Timestamp(frame.index[-1]).to_pydatetime()
            if source_timestamp.tzinfo is None:
                source_timestamp = source_timestamp.replace(tzinfo=UTC)
            return PriceQuote(
                symbol=symbol,
                portfolio=portfolio,
                price=float(frame["Close"].iloc[-1]),
                source="yahoo:5m",
                source_timestamp=source_timestamp.astimezone(UTC),
                captured_at=captured_at.astimezone(UTC),
            )

        if not self._kraken_loaded:
            self.kraken.load_markets()
            self._kraken_loaded = True
        rows = self.kraken.fetch_ohlcv(symbol, timeframe="5m", limit=2)
        if not rows:
            raise ValueError(f"No five-minute Kraken quote returned for {symbol}")
        latest = rows[-1]
        return PriceQuote(
            symbol=symbol,
            portfolio=portfolio,
            price=float(latest[4]),
            source="kraken:5m",
            source_timestamp=datetime.fromtimestamp(float(latest[0]) / 1000, tz=UTC),
            captured_at=captured_at.astimezone(UTC),
        )

    def close(self) -> None:
        if self._owns_kraken:
            close = getattr(self.kraken, "close", None)
            if callable(close):
                close()
