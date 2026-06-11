from __future__ import annotations

import json
from collections.abc import Callable
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
from io import StringIO
from pathlib import Path
from urllib.request import Request, urlopen

import pandas as pd

from tradex.config.settings import ROOT

WIKIPEDIA_URL = "https://en.wikipedia.org/wiki/List_of_S%26P_500_companies"
DEFAULT_SNAPSHOT_PATH = ROOT / "tradex" / "stocks" / "data" / "sp500.json"


@dataclass(frozen=True)
class StockConstituent:
    symbol: str
    yahoo_symbol: str
    security: str
    sector: str
    sub_industry: str
    date_added: str


@dataclass(frozen=True)
class StockUniverse:
    name: str
    source_url: str
    retrieved_at: str
    constituents: tuple[StockConstituent, ...]

    @property
    def symbols(self) -> tuple[str, ...]:
        return tuple(item.yahoo_symbol for item in self.constituents)


def normalize_yahoo_symbol(symbol: str) -> str:
    return symbol.strip().upper().replace(".", "-")


def _clean_cell(value: object) -> str:
    if pd.isna(value):
        return ""
    return str(value).strip()


def parse_constituents(table: pd.DataFrame) -> tuple[StockConstituent, ...]:
    required = {
        "Symbol",
        "Security",
        "GICS Sector",
        "GICS Sub-Industry",
        "Date added",
    }
    missing = required - set(table.columns)
    if missing:
        raise ValueError(f"S&P 500 table is missing columns: {sorted(missing)}")

    constituents = [
        StockConstituent(
            symbol=_clean_cell(row["Symbol"]).upper(),
            yahoo_symbol=normalize_yahoo_symbol(_clean_cell(row["Symbol"])),
            security=_clean_cell(row["Security"]),
            sector=_clean_cell(row["GICS Sector"]),
            sub_industry=_clean_cell(row["GICS Sub-Industry"]),
            date_added=_clean_cell(row["Date added"]),
        )
        for _, row in table.iterrows()
    ]
    return tuple(sorted(constituents, key=lambda item: item.symbol))


def download_html(url: str) -> str:
    request = Request(
        url,
        headers={"User-Agent": "TradeX/0.1 (+https://github.com/sansgamesolutions-svg/tradex)"},
    )
    with urlopen(request, timeout=30) as response:
        return response.read().decode("utf-8")


def refresh_universe(
    output_path: Path = DEFAULT_SNAPSHOT_PATH,
    *,
    source_url: str = WIKIPEDIA_URL,
    retrieved_at: datetime | None = None,
    html_loader: Callable[[str], str] = download_html,
) -> StockUniverse:
    tables = pd.read_html(
        StringIO(html_loader(source_url)),
        attrs={"id": "constituents"},
    )
    if not tables:
        raise ValueError("Could not find the S&P 500 constituents table")

    timestamp = retrieved_at or datetime.now(UTC)
    universe = StockUniverse(
        name="S&P 500",
        source_url=source_url,
        retrieved_at=timestamp.isoformat(),
        constituents=parse_constituents(tables[0]),
    )
    write_universe(universe, output_path)
    return universe


def write_universe(universe: StockUniverse, path: Path = DEFAULT_SNAPSHOT_PATH) -> None:
    payload = {
        "name": universe.name,
        "source_url": universe.source_url,
        "retrieved_at": universe.retrieved_at,
        "constituents": [asdict(item) for item in universe.constituents],
    }
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def load_universe(path: Path = DEFAULT_SNAPSHOT_PATH) -> StockUniverse:
    payload = json.loads(path.read_text(encoding="utf-8"))
    return StockUniverse(
        name=payload["name"],
        source_url=payload["source_url"],
        retrieved_at=payload["retrieved_at"],
        constituents=tuple(StockConstituent(**item) for item in payload["constituents"]),
    )
