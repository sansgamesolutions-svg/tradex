from __future__ import annotations

import pytest

from tradex.drill.broker import SimulatedBroker
from tradex.execution import OrderRequest, OrderResult


def test_simulated_broker_implements_preview_and_internal_submit():
    request = OrderRequest(symbol="AAPL", side="BUY", quantity=1)

    def fill(order):
        return OrderResult(
            order_id="SIM-1",
            status="filled",
            symbol=order.symbol,
            side=order.side,
            quantity=order.quantity,
            filled=order.quantity,
            remaining=0,
            average_fill_price=100,
            broker="SIMULATION",
        )

    broker = SimulatedBroker(fill)

    assert broker.preview(request).venue == "internal-paper-ledger"
    assert broker.submit(request).broker == "SIMULATION"


def test_simulated_broker_cannot_route_without_internal_handler():
    with pytest.raises(RuntimeError, match="internal fill handler"):
        SimulatedBroker().submit(OrderRequest(symbol="AAPL", side="BUY", quantity=1))
