from types import SimpleNamespace

import pytest

from tradex.execution import (
    IBKRBroker,
    IBKRConfig,
    KrakenBroker,
    KrakenConfig,
    OrderRequest,
)


class FakeIB:
    def __init__(self) -> None:
        self.connected = False
        self.connect_args = None
        self.placed = None

    def connect(self, *args, **kwargs):
        self.connected = True
        self.connect_args = (args, kwargs)

    def disconnect(self):
        self.connected = False

    def isConnected(self):
        return self.connected

    def qualifyContracts(self, *contracts):
        return list(contracts)

    def placeOrder(self, contract, order):
        order.orderId = 42
        self.placed = (contract, order)
        status = SimpleNamespace(
            status="PendingSubmit",
            filled=0,
            remaining=order.totalQuantity,
            avgFillPrice=0,
        )
        return SimpleNamespace(contract=contract, order=order, orderStatus=status)


def test_submit_stock_market_buy():
    client = FakeIB()
    config = IBKRConfig(port=7497, client_id=17, account="DU123")
    broker = IBKRBroker(config=config, client=client)

    result = broker.buy("aapl", 3)

    contract, order = client.placed
    assert client.connect_args[0] == ("127.0.0.1", 7497)
    assert client.connect_args[1]["clientId"] == 17
    assert contract.secType == "STK"
    assert contract.symbol == "AAPL"
    assert contract.exchange == "SMART"
    assert order.action == "BUY"
    assert order.orderType == "MKT"
    assert order.account == "DU123"
    assert result.order_id == "42"
    assert result.status == "PendingSubmit"
    assert result.broker == "IBKR"


def test_submit_forex_limit_sell():
    client = FakeIB()
    broker = IBKRBroker(client=client)
    request = OrderRequest(
        symbol="EUR/USD",
        side="SELL",
        quantity=10_000,
        asset_type="FOREX",
        order_type="LIMIT",
        limit_price=1.12,
        time_in_force="GTC",
    )

    broker.submit(request)

    contract, order = client.placed
    assert contract.secType == "CASH"
    assert contract.symbol == "EUR"
    assert contract.currency == "USD"
    assert contract.exchange == "IDEALPRO"
    assert order.orderType == "LMT"
    assert order.lmtPrice == 1.12
    assert order.tif == "GTC"


def test_ibkr_rejects_crypto():
    request = OrderRequest(symbol="BTC", side="BUY", quantity=0.01, asset_type="CRYPTO")

    with pytest.raises(ValueError, match="Kraken"):
        IBKRBroker(client=FakeIB()).build_contract(request)


@pytest.mark.parametrize("quantity", [0, -1, float("inf"), float("nan")])
def test_rejects_invalid_quantity(quantity):
    with pytest.raises(ValueError, match="quantity"):
        OrderRequest(symbol="AAPL", side="BUY", quantity=quantity)


def test_limit_order_requires_price():
    with pytest.raises(ValueError, match="limit_price"):
        OrderRequest(
            symbol="AAPL",
            side="BUY",
            quantity=1,
            order_type="LIMIT",
        )


class FakeKraken:
    def __init__(self) -> None:
        self.loaded = False
        self.created = None
        self.closed = False

    def load_markets(self):
        self.loaded = True
        return {}

    def market(self, symbol):
        return {"symbol": symbol, "spot": True}

    def amount_to_precision(self, symbol, amount):
        return f"{amount:.6f}"

    def price_to_precision(self, symbol, price):
        return f"{price:.2f}"

    def create_order(self, symbol, order_type, side, amount, price=None, params=None):
        self.created = (symbol, order_type, side, amount, price, params)
        return {
            "id": "ORDER-123",
            "status": "open",
            "symbol": symbol,
            "side": side,
            "amount": amount,
            "filled": 0,
            "remaining": amount,
            "average": None,
        }

    def close(self):
        self.closed = True


def test_kraken_market_buy_uses_spot_pair():
    client = FakeKraken()
    broker = KrakenBroker(
        config=KrakenConfig(api_key="key", api_secret="secret"),
        client=client,
    )
    request = OrderRequest(
        symbol="btc",
        side="BUY",
        quantity=0.01234567,
        asset_type="CRYPTO",
    )

    result = broker.submit(request)

    assert client.loaded
    assert client.created == ("BTC/USD", "market", "buy", 0.012346, None, {})
    assert result.order_id == "ORDER-123"
    assert result.broker == "KRAKEN"


def test_kraken_limit_sell_applies_precision():
    client = FakeKraken()
    broker = KrakenBroker(
        config=KrakenConfig(api_key="key", api_secret="secret"),
        client=client,
    )
    request = OrderRequest(
        symbol="ETH/USD",
        side="SELL",
        quantity=1.2345678,
        asset_type="CRYPTO",
        order_type="LIMIT",
        limit_price=3456.789,
    )

    broker.submit(request)

    assert client.created == (
        "ETH/USD",
        "limit",
        "sell",
        1.234568,
        3456.79,
        {"timeInForce": "GTC"},
    )


def test_kraken_requires_credentials_before_network_call():
    client = FakeKraken()
    broker = KrakenBroker(config=KrakenConfig(), client=client)
    request = OrderRequest(symbol="BTC", side="BUY", quantity=0.1, asset_type="CRYPTO")

    with pytest.raises(ValueError, match="TRADEX_KRAKEN_API_KEY"):
        broker.submit(request)

    assert not client.loaded


@pytest.mark.parametrize(
    ("input_symbol", "expected"),
    [("BTC", "BTC/USD"), ("BTCUSD", "BTC/USD"), ("BTC-USD", "BTC/USD")],
)
def test_kraken_symbol_normalization(input_symbol, expected):
    request = OrderRequest(
        symbol=input_symbol,
        side="BUY",
        quantity=0.1,
        asset_type="CRYPTO",
    )

    assert KrakenBroker(client=FakeKraken()).symbol_for(request) == expected
