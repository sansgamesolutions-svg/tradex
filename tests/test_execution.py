from types import SimpleNamespace

import pytest

from tradex.execution.ibkr import IBKRBroker, IBKRConfig, OrderRequest


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
    assert result.order_id == 42
    assert result.status == "PendingSubmit"


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


def test_crypto_uses_paxos_by_default():
    request = OrderRequest(
        symbol="BTC",
        side="BUY",
        quantity=0.01,
        asset_type="CRYPTO",
    )

    contract = IBKRBroker(client=FakeIB()).build_contract(request)

    assert contract.secType == "CRYPTO"
    assert contract.exchange == "PAXOS"
    assert contract.currency == "USD"


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
