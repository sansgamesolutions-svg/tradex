from __future__ import annotations

import os
from collections.abc import Mapping, Sequence
from pathlib import Path
from typing import Protocol

from dotenv import dotenv_values

from tradex.config.settings import ROOT


class SecretProvider(Protocol):
    """Source for secret values without exposing them through general settings."""

    def get(self, name: str) -> str | None: ...


class EnvironmentSecretProvider:
    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self.environ = environ if environ is not None else os.environ

    def get(self, name: str) -> str | None:
        value = self.environ.get(name)
        return value if value else None


class FileSecretProvider:
    """Read secrets from paths supplied through NAME_FILE environment variables."""

    def __init__(self, environ: Mapping[str, str] | None = None) -> None:
        self.environ = environ if environ is not None else os.environ

    def get(self, name: str) -> str | None:
        path_value = self.environ.get(f"{name}_FILE")
        if not path_value:
            return None

        path = Path(path_value).expanduser()
        try:
            value = path.read_text(encoding="utf-8").strip()
        except OSError as exc:
            raise ValueError(f"Could not read secret file configured by {name}_FILE") from exc
        return value if value else None


class DotEnvSecretProvider:
    """Read an ignored local .env file without modifying process environment."""

    def __init__(self, path: Path | None = None) -> None:
        self.path = path or ROOT / ".env"
        self._values: dict[str, str | None] | None = None

    def get(self, name: str) -> str | None:
        if self._values is None:
            self._values = dotenv_values(self.path) if self.path.exists() else {}
        value = self._values.get(name)
        return value if value else None


class SecretResolver:
    """Resolve platform credentials from an ordered chain of secret providers."""

    def __init__(self, providers: Sequence[SecretProvider] | None = None) -> None:
        self.providers = tuple(
            providers
            or (
                EnvironmentSecretProvider(),
                FileSecretProvider(),
                DotEnvSecretProvider(),
            )
        )

    @staticmethod
    def variable_name(platform: str, field: str) -> str:
        normalized_platform = platform.strip().replace("-", "_").upper()
        normalized_field = field.strip().replace("-", "_").upper()
        return f"TRADEX_{normalized_platform}_{normalized_field}"

    def get(
        self,
        platform: str,
        field: str,
        *,
        required: bool = False,
    ) -> str:
        name = self.variable_name(platform, field)
        for provider in self.providers:
            value = provider.get(name)
            if value:
                return value
        if required:
            raise ValueError(f"Missing secret {name} or {name}_FILE")
        return ""


secrets = SecretResolver()
