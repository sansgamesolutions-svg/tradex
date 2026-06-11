from __future__ import annotations

from collections.abc import Callable, Iterable
from dataclasses import dataclass

from tradex.execution.base import TradingPlatform
from tradex.execution.models import AssetType, OrderRequest

PlatformFactory = Callable[[], TradingPlatform]


@dataclass(frozen=True)
class PlatformRegistration:
    name: str
    factory: PlatformFactory
    asset_types: frozenset[AssetType]


class PlatformRegistry:
    """Register platform adapters and select defaults by asset type."""

    def __init__(self) -> None:
        self._platforms: dict[str, PlatformRegistration] = {}
        self._defaults: dict[AssetType, str] = {}

    def register(
        self,
        name: str,
        factory: PlatformFactory,
        asset_types: Iterable[AssetType],
        *,
        default_for: Iterable[AssetType] = (),
    ) -> None:
        normalized_name = name.strip().lower()
        supported = frozenset(asset_types)
        defaults = frozenset(default_for)
        if not normalized_name:
            raise ValueError("platform name is required")
        if not supported:
            raise ValueError("at least one asset type is required")
        if normalized_name in self._platforms:
            raise ValueError(f"platform {normalized_name} is already registered")
        unsupported_defaults = defaults - supported
        if unsupported_defaults:
            asset_type = sorted(unsupported_defaults)[0]
            raise ValueError(f"{normalized_name} does not support {asset_type}")

        self._platforms[normalized_name] = PlatformRegistration(
            name=normalized_name,
            factory=factory,
            asset_types=supported,
        )
        for asset_type in defaults:
            self._defaults[asset_type] = normalized_name

    def names(self) -> tuple[str, ...]:
        return tuple(sorted(self._platforms))

    def create(
        self,
        request: OrderRequest,
        platform: str | None = None,
    ) -> TradingPlatform:
        name = platform.strip().lower() if platform else self._defaults.get(request.asset_type)
        if not name:
            raise ValueError(f"No default platform configured for {request.asset_type}")

        registration = self._platforms.get(name)
        if registration is None:
            available = ", ".join(self.names())
            raise ValueError(f"Unknown platform {name}. Available platforms: {available}")
        if request.asset_type not in registration.asset_types:
            raise ValueError(f"{name} does not support {request.asset_type} orders")
        return registration.factory()


def build_default_registry() -> PlatformRegistry:
    from tradex.execution.ibkr import IBKRBroker
    from tradex.execution.kraken import KrakenBroker

    registry = PlatformRegistry()
    registry.register(
        "ibkr",
        IBKRBroker,
        ("STOCK", "FOREX"),
        default_for=("STOCK", "FOREX"),
    )
    registry.register(
        "kraken",
        KrakenBroker,
        ("CRYPTO",),
        default_for=("CRYPTO",),
    )
    return registry


platforms = build_default_registry()
