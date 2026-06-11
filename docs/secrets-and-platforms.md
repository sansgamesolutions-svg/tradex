# Trading Platforms and Secrets

TradeX separates platform configuration from credentials:

- Non-secret settings such as hosts, ports, and timeouts belong in `config.yaml`.
- Credentials are resolved at runtime and must not be stored in `config.yaml`.
- The CLI routes orders through the platform registry instead of importing brokers directly.

## Secret Resolution

For any platform and credential field, TradeX uses this naming convention:

```text
TRADEX_<PLATFORM>_<FIELD>
TRADEX_<PLATFORM>_<FIELD>_FILE
```

For example, Kraken uses:

```text
TRADEX_KRAKEN_API_KEY
TRADEX_KRAKEN_API_SECRET
```

Values are resolved in this order:

1. Process environment variables
2. Files referenced by matching `_FILE` environment variables
3. The ignored project-root `.env` file

The `_FILE` convention supports Docker, Kubernetes, and other systems that mount
secrets as files. Platform credential fields use redacted dataclass
representations to reduce accidental logging.

## Adding a Platform

Implement the `TradingPlatform` protocol:

```python
class NewPlatform:
    name = "new_platform"
    supported_asset_types = frozenset(("CRYPTO",))

    def preview(self, request): ...
    def submit(self, request): ...
    def close(self): ...
```

Resolve credentials without adding them to general settings:

```python
from tradex.config.secrets import secrets

api_key = secrets.get("new_platform", "api_key", required=True)
```

Register the adapter:

```python
platforms.register(
    "new_platform",
    NewPlatform,
    ("CRYPTO",),
)
```

The existing CLI can then select it with `--platform new_platform`.
