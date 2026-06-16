from __future__ import annotations

from click.testing import CliRunner

from tradex.__main__ import cli


def test_auto_profiles_cli_lists_one_day_drill():
    result = CliRunner().invoke(cli, ["auto", "profiles"])

    assert result.exit_code == 0
    assert "one-day-drill" in result.output
    assert "SIMULATED" in result.output
