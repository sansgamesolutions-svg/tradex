from pathlib import Path

import pytest

from tradex.config.secrets import (
    DotEnvSecretProvider,
    EnvironmentSecretProvider,
    FileSecretProvider,
    SecretResolver,
)
from tradex.execution import IBKRConfig, KrakenConfig


def test_environment_secret_has_priority(tmp_path: Path):
    secret_file = tmp_path / "api-key"
    secret_file.write_text("file-value\n", encoding="utf-8")
    environ = {
        "TRADEX_KRAKEN_API_KEY": "environment-value",
        "TRADEX_KRAKEN_API_KEY_FILE": str(secret_file),
    }
    resolver = SecretResolver(
        (
            EnvironmentSecretProvider(environ),
            FileSecretProvider(environ),
        )
    )

    assert resolver.get("kraken", "api_key") == "environment-value"


def test_file_secret_supports_docker_and_kubernetes_mounts(tmp_path: Path):
    secret_file = tmp_path / "api-secret"
    secret_file.write_text("mounted-secret\n", encoding="utf-8")
    environ = {"TRADEX_KRAKEN_API_SECRET_FILE": str(secret_file)}
    resolver = SecretResolver((FileSecretProvider(environ),))

    assert resolver.get("kraken", "api_secret") == "mounted-secret"


def test_dotenv_secret_is_loaded_without_mutating_environment(tmp_path: Path):
    dotenv_path = tmp_path / ".env"
    dotenv_path.write_text("TRADEX_KRAKEN_API_KEY=dotenv-value\n", encoding="utf-8")
    resolver = SecretResolver((DotEnvSecretProvider(dotenv_path),))

    assert resolver.get("kraken", "api_key") == "dotenv-value"


def test_required_secret_error_only_names_variable():
    resolver = SecretResolver((EnvironmentSecretProvider({}),))

    with pytest.raises(ValueError, match="TRADEX_NEW_BROKER_TOKEN"):
        resolver.get("new-broker", "token", required=True)


def test_platform_config_repr_redacts_credentials():
    kraken = KrakenConfig(api_key="visible-key", api_secret="visible-secret")
    ibkr = IBKRConfig(account="DU123456")

    assert "visible-key" not in repr(kraken)
    assert "visible-secret" not in repr(kraken)
    assert "DU123456" not in repr(ibkr)
