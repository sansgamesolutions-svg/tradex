from dataclasses import dataclass

import pytest

from tradex.execution import OrderPreview, OrderRequest, OrderResult, PlatformRegistry


@dataclass
class FakePlatform:
    name: str = "future"
    supported_asset_types = frozenset(("CRYPTO",))
    closed: bool = False

    def preview(self, request):
        return OrderPreview(
            platform=self.name,
            venue="test",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            order_type=request.order_type,
        )

    def submit(self, request):
        return OrderResult(
            order_id="1",
            status="open",
            symbol=request.symbol,
            side=request.side,
            quantity=request.quantity,
            filled=0,
            remaining=request.quantity,
            average_fill_price=0,
            broker=self.name.upper(),
        )

    def close(self):
        self.closed = True


def test_registry_routes_to_default_platform():
    registry = PlatformRegistry()
    registry.register("future", FakePlatform, ("CRYPTO",), default_for=("CRYPTO",))
    request = OrderRequest(symbol="BTC", side="BUY", quantity=0.1, asset_type="CRYPTO")

    platform = registry.create(request)

    assert platform.name == "future"


def test_registry_allows_explicit_platform_override():
    registry = PlatformRegistry()
    registry.register("first", FakePlatform, ("CRYPTO",), default_for=("CRYPTO",))
    registry.register("second", lambda: FakePlatform(name="second"), ("CRYPTO",))
    request = OrderRequest(symbol="BTC", side="BUY", quantity=0.1, asset_type="CRYPTO")

    platform = registry.create(request, "second")

    assert platform.name == "second"


def test_registry_rejects_unsupported_asset_type():
    registry = PlatformRegistry()
    registry.register("future", FakePlatform, ("CRYPTO",))
    request = OrderRequest(symbol="AAPL", side="BUY", quantity=1, asset_type="STOCK")

    with pytest.raises(ValueError, match="does not support STOCK"):
        registry.create(request, "future")


def test_registry_rejects_duplicate_platform_name():
    registry = PlatformRegistry()
    registry.register("future", FakePlatform, ("CRYPTO",))

    with pytest.raises(ValueError, match="already registered"):
        registry.register("future", FakePlatform, ("CRYPTO",))


def test_invalid_default_does_not_partially_register_platform():
    registry = PlatformRegistry()

    with pytest.raises(ValueError, match="does not support STOCK"):
        registry.register("future", FakePlatform, ("CRYPTO",), default_for=("STOCK",))

    assert registry.names() == ()
