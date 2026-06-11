from datetime import UTC, datetime

from tradex.crypto.universe import (
    CryptoUniverse,
    load_universe,
    parse_markets,
    refresh_universe,
    write_universe,
)


def sample_markets():
    return {
        "BTC/USD": {
            "id": "XXBTZUSD",
            "symbol": "BTC/USD",
            "base": "BTC",
            "quote": "USD",
            "spot": True,
            "active": True,
        },
        "ETH/USD": {
            "id": "XETHZUSD",
            "symbol": "ETH/USD",
            "base": "ETH",
            "quote": "USD",
            "spot": True,
            "active": True,
        },
        "USDT/USD": {
            "id": "USDTZUSD",
            "symbol": "USDT/USD",
            "base": "USDT",
            "quote": "USD",
            "spot": True,
            "active": True,
        },
        "XAUT/USD": {
            "id": "XAUTUSD",
            "symbol": "XAUT/USD",
            "base": "XAUT",
            "quote": "USD",
            "spot": True,
            "active": True,
        },
        "BTC/EUR": {
            "id": "XXBTZEUR",
            "symbol": "BTC/EUR",
            "base": "BTC",
            "quote": "EUR",
            "spot": True,
            "active": True,
        },
        "OLD/USD": {
            "id": "OLDUSD",
            "symbol": "OLD/USD",
            "base": "OLD",
            "quote": "USD",
            "spot": True,
            "active": False,
        },
        "BTC/USD:USD": {
            "id": "BTCUSD-PERP",
            "symbol": "BTC/USD:USD",
            "base": "BTC",
            "quote": "USD",
            "spot": False,
            "active": True,
        },
    }


class FakeMarketClient:
    def __init__(self):
        self.closed = False

    def load_markets(self):
        return sample_markets()

    def close(self):
        self.closed = True


def test_market_parser_keeps_active_usd_crypto_spot_only():
    markets = parse_markets(sample_markets())

    assert [market.symbol for market in markets] == ["BTC/USD", "ETH/USD"]


def test_crypto_snapshot_round_trip_is_deterministic(tmp_path):
    path = tmp_path / "kraken-usd.json"
    universe = CryptoUniverse(
        name="Kraken USD Spot",
        exchange="kraken",
        source="kraken:test",
        retrieved_at="2026-06-11T00:00:00+00:00",
        markets=parse_markets(sample_markets()),
    )

    write_universe(universe, path)
    first = path.read_text(encoding="utf-8")
    write_universe(universe, path)

    assert path.read_text(encoding="utf-8") == first
    assert load_universe(path) == universe


def test_refresh_uses_injected_public_market_client(tmp_path):
    client = FakeMarketClient()
    path = tmp_path / "kraken-usd.json"

    universe = refresh_universe(
        path,
        client=client,
        retrieved_at=datetime(2026, 6, 11, tzinfo=UTC),
    )

    assert universe.symbols == ("BTC/USD", "ETH/USD")
    assert not client.closed
    assert load_universe(path) == universe
