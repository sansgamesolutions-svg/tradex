from datetime import UTC, datetime

import pandas as pd

from tradex.stocks.universe import (
    StockUniverse,
    load_universe,
    normalize_yahoo_symbol,
    parse_constituents,
    refresh_universe,
    write_universe,
)


def sample_table():
    return pd.DataFrame(
        [
            {
                "Symbol": "MSFT",
                "Security": "Microsoft",
                "GICS Sector": "Information Technology",
                "GICS Sub-Industry": "Systems Software",
                "Date added": "1994-06-01",
            },
            {
                "Symbol": "BRK.B",
                "Security": "Berkshire Hathaway",
                "GICS Sector": "Financials",
                "GICS Sub-Industry": "Multi-Sector Holdings",
                "Date added": "2010-02-16",
            },
        ]
    )


def test_yahoo_symbol_normalization():
    assert normalize_yahoo_symbol("brk.b") == "BRK-B"


def test_constituents_are_parsed_and_sorted():
    constituents = parse_constituents(sample_table())

    assert [item.symbol for item in constituents] == ["BRK.B", "MSFT"]
    assert constituents[0].yahoo_symbol == "BRK-B"


def test_snapshot_round_trip_is_deterministic(tmp_path):
    path = tmp_path / "sp500.json"
    universe = StockUniverse(
        name="S&P 500",
        source_url="https://example.test",
        retrieved_at="2026-06-11T00:00:00+00:00",
        constituents=parse_constituents(sample_table()),
    )

    write_universe(universe, path)
    first = path.read_text(encoding="utf-8")
    write_universe(universe, path)

    assert path.read_text(encoding="utf-8") == first
    assert load_universe(path) == universe


def test_refresh_uses_constituents_table(monkeypatch, tmp_path):
    calls = []

    def fake_read_html(source, attrs):
        calls.append((source.read(), attrs))
        return [sample_table()]

    monkeypatch.setattr(pd, "read_html", fake_read_html)
    path = tmp_path / "sp500.json"
    retrieved = datetime(2026, 6, 11, tzinfo=UTC)

    universe = refresh_universe(
        path,
        source_url="https://example.test/sp500",
        retrieved_at=retrieved,
        html_loader=lambda url: f"<html>{url}</html>",
    )

    assert calls == [
        (
            "<html>https://example.test/sp500</html>",
            {"id": "constituents"},
        )
    ]
    assert universe.retrieved_at == retrieved.isoformat()
    assert load_universe(path) == universe
