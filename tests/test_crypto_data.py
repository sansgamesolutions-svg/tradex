from datetime import UTC, datetime

from tradex.crypto.data import KrakenMarketData


class FakeOHLCVClient:
    def __init__(self):
        self.loaded = False
        self.request = None

    def load_markets(self):
        self.loaded = True
        return {}

    def fetch_ohlcv(self, symbol, timeframe="1d", since=None, limit=None):
        self.request = (symbol, timeframe, since, limit)
        return [
            [1781049600000, 100, 110, 90, 105, 1_000],
            [1781136000000, 105, 115, 100, 110, 2_000],
        ]

    def close(self):
        pass


def test_kraken_daily_data_normalizes_columns_and_drops_open_day():
    client = FakeOHLCVClient()
    data = KrakenMarketData(client=client)

    frame = data.fetch_daily(
        "BTC/USD",
        now=datetime(2026, 6, 11, 12, tzinfo=UTC),
    )

    assert client.loaded
    assert client.request == ("BTC/USD", "1d", None, 720)
    assert list(frame.columns) == ["open", "high", "low", "close", "volume"]
    assert len(frame) == 1
    assert frame.iloc[0]["close"] == 105
