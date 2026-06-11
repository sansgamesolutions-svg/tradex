from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Protocol

import ccxt

from tradex.config.settings import ROOT, settings

DEFAULT_SNAPSHOT_PATH = ROOT / "tradex" / "crypto" / "data" / "kraken-usd.json"
KRAKEN_MARKETS_SOURCE = "kraken:public/AssetPairs"

_EXCLUDED_BASES = frozenset(
    {
        "AUD",
        "CAD",
        "CHF",
        "DAI",
        "EUR",
        "GBP",
        "JPY",
        "PAXG",
        "PYUSD",
        "USD",
        "USDC",
        "USDT",
        "WBTC",
        "WETH",
        "XAUT",
    }
)
_LEVERAGED_SUFFIXES = ("BULL", "BEAR", "DOWN", "UP")


class MarketClient(Protocol):
    def load_markets(self) -> dict[str, Any]: ...


@dataclass(frozen=True)
class CryptoMarket:
    symbol: str
    market_id: str
    base: str
    quote: str
    active: bool


@dataclass(frozen=True)
class CryptoUniverse:
    name: str
    exchange: str
    source: str
    retrieved_at: str
    markets: tuple[CryptoMarket, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(market.symbol for market in self.markets)


def is_eligible_market(market: Mapping[str, Any]) -> bool:
    symbol = str(market.get("symbol") or "")
    base = str(market.get("base") or "").upper()
    quote = str(market.get("quote") or "").upper()
    active = market.get("active")
    if not market.get("spot") or active is False or quote != "USD":
        return False
    if not symbol or ":" in symbol or ".d" in symbol.lower():
        return False
    if base in _EXCLUDED_BASES or base.endswith(_LEVERAGED_SUFFIXES):
        return False
    return True


def parse_markets(markets: Mapping[str, Mapping[str, Any]]) -> tuple[CryptoMarket, ...]:
    parsed = [
        CryptoMarket(
            symbol=str(market["symbol"]),
            market_id=str(market.get("id") or market["symbol"]),
            base=str(market["base"]).upper(),
            quote=str(market["quote"]).upper(),
            active=market.get("active") is not False,
        )
        for market in markets.values()
        if is_eligible_market(market)
    ]
    return tuple(sorted(parsed, key=lambda market: market.symbol))


def refresh_universe(
    output_path: Path = DEFAULT_SNAPSHOT_PATH,
    *,
    client: MarketClient | None = None,
    retrieved_at: datetime | None = None,
) -> CryptoUniverse:
    owns_client = client is None
    market_client = client or ccxt.kraken(
        {
            "enableRateLimit": True,
            "timeout": int(settings.kraken_timeout),
            "options": {"defaultType": "spot"},
        }
    )
    try:
        markets = market_client.load_markets()
    finally:
        if owns_client:
            close = getattr(market_client, "close", None)
            if callable(close):
                close()

    universe = CryptoUniverse(
        name="Kraken USD Spot",
        exchange="kraken",
        source=KRAKEN_MARKETS_SOURCE,
        retrieved_at=(retrieved_at or datetime.now(UTC)).isoformat(),
        markets=parse_markets(markets),
    )
    write_universe(universe, output_path)
    return universe


def write_universe(
    universe: CryptoUniverse,
    path: Path = DEFAULT_SNAPSHOT_PATH,
) -> None:
    payload = {
        "name": universe.name,
        "exchange": universe.exchange,
        "source": universe.source,
        "retrieved_at": universe.retrieved_at,
        "markets": [asdict(market) for market in universe.markets],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_universe(path: Path = DEFAULT_SNAPSHOT_PATH) -> CryptoUniverse:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return CryptoUniverse(
        name=payload["name"],
        exchange=payload["exchange"],
        source=payload["source"],
        retrieved_at=payload["retrieved_at"],
        markets=tuple(CryptoMarket(**market) for market in payload["markets"]),
    )
