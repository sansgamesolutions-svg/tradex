from pathlib import Path

import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option()
def cli():
    """TradeX — multi-asset trade prediction CLI."""


@cli.command()
@click.option("--asset", required=True, help="Asset symbol, e.g. BTC, AAPL, EUR/USD")
@click.option(
    "--timeframe", default="1d", show_default=True, help="Candle timeframe (1m/5m/15m/1h/4h/1d/1w)"
)
@click.option(
    "--model",
    default="xgboost",
    show_default=True,
    type=click.Choice(["xgboost", "random_forest", "lstm"]),
)
def predict(asset: str, timeframe: str, model: str) -> None:
    """Generate a BUY/SELL/HOLD prediction for an asset."""
    from tradex.data.fetcher import fetch
    from tradex.data.preprocessor import build_features
    from tradex.indicators.technical import add_indicators
    from tradex.signals.combiner import SignalCombiner

    console.print(f"[bold blue]Fetching {asset} ({timeframe})...[/bold blue]")
    raw_df = fetch(asset, timeframe)
    raw_df = add_indicators(raw_df)
    features = build_features(raw_df)

    combiner = SignalCombiner(model_name=model, asset=asset, timeframe=timeframe)
    signal = combiner.predict(features, raw_df)

    color = {"BUY": "green", "SELL": "red", "HOLD": "yellow"}[signal]
    console.print(f"Signal for [bold]{asset}[/bold]: [{color}]{signal}[/{color}]")


@cli.command()
@click.option("--asset", required=True)
@click.option("--timeframe", default="1d", show_default=True)
@click.option("--start", required=True, help="Start date YYYY-MM-DD")
@click.option("--end", default=None, help="End date YYYY-MM-DD (default: today)")
@click.option(
    "--model",
    default="xgboost",
    show_default=True,
    type=click.Choice(["xgboost", "random_forest", "lstm"]),
)
def backtest(asset: str, timeframe: str, start: str, end: str | None, model: str) -> None:
    """Run a historical backtest for an asset."""
    from tradex.backtester.engine import Backtester
    from tradex.data.fetcher import fetch
    from tradex.data.preprocessor import build_features
    from tradex.indicators.technical import add_indicators

    console.print(f"[bold blue]Backtesting {asset} from {start}...[/bold blue]")
    raw_df = fetch(asset, timeframe, start=start, end=end)
    raw_df = add_indicators(raw_df)
    features = build_features(raw_df)

    bt = Backtester(model_name=model)
    results = bt.run(features, raw_df)
    bt.print_report(results)


@cli.command("fetch")
@click.option("--asset", required=True)
@click.option("--timeframe", default="1d", show_default=True)
@click.option("--start", default=None, help="Start date YYYY-MM-DD")
@click.option("--end", default=None, help="End date YYYY-MM-DD")
def fetch_cmd(asset: str, timeframe: str, start: str | None, end: str | None) -> None:
    """Fetch and cache market data for an asset."""
    from tradex.data.fetcher import fetch

    df = fetch(asset, timeframe, start=start, end=end, force_refresh=True)
    console.print(f"[green]Fetched {len(df)} rows for {asset} ({timeframe})[/green]")


@cli.command()
@click.option("--asset", required=True)
@click.option("--timeframe", default="1d", show_default=True)
@click.option(
    "--model",
    default="xgboost",
    show_default=True,
    type=click.Choice(["xgboost", "random_forest", "lstm"]),
)
@click.option("--start", default=None)
@click.option("--end", default=None)
def train(asset: str, timeframe: str, model: str, start: str | None, end: str | None) -> None:
    """Train a model on historical data and save the artifact."""
    from tradex.data.fetcher import fetch
    from tradex.data.preprocessor import build_features, make_target, train_test_split
    from tradex.indicators.technical import add_indicators
    from tradex.models import get_model

    console.print(f"[bold blue]Training {model} on {asset} ({timeframe})...[/bold blue]")
    raw_df = fetch(asset, timeframe, start=start, end=end)
    raw_df = add_indicators(raw_df)
    X = build_features(raw_df)
    y = make_target(raw_df)

    X_train, X_test, y_train, y_test = train_test_split(X, y)

    m = get_model(model)
    m.fit(X_train, y_train)

    metrics = m.evaluate(X_test, y_test)
    path = m.save(asset, timeframe)

    console.print(f"[green]Saved to {path}[/green]")
    for k, v in metrics.items():
        console.print(f"  {k}: {v:.4f}")


@cli.group()
def stocks() -> None:
    """Screen and train daily S&P 500 stock models."""


@stocks.command("refresh-universe")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Snapshot JSON path (default: packaged S&P 500 snapshot)",
)
def refresh_stock_universe(output) -> None:
    """Refresh the versioned S&P 500 constituent snapshot."""
    from tradex.stocks.universe import DEFAULT_SNAPSHOT_PATH, refresh_universe

    path = output or DEFAULT_SNAPSHOT_PATH
    universe = refresh_universe(path)
    console.print(f"[green]Saved {len(universe.constituents)} constituents to {path}[/green]")


@stocks.command("qualify")
@click.option(
    "--model",
    default="xgboost",
    show_default=True,
    type=click.Choice(["xgboost", "random_forest", "lstm"]),
)
@click.option(
    "--report",
    type=click.Path(path_type=Path),
    default=None,
    help="Output JSON report path",
)
@click.option(
    "--universe",
    "universe_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Universe snapshot path",
)
@click.option("--start", default=None, help="Training history start date YYYY-MM-DD")
def qualify_stocks(model: str, report, universe_path, start: str | None) -> None:
    """Screen S&P 500 stocks and run walk-forward model qualification."""
    from datetime import UTC, datetime

    from tradex.config.settings import ROOT
    from tradex.stocks import StockQualificationPipeline
    from tradex.stocks.universe import (
        DEFAULT_SNAPSHOT_PATH,
        load_universe,
    )

    snapshot = load_universe(universe_path or DEFAULT_SNAPSHOT_PATH)
    report_path = report or (
        ROOT / "reports" / f"stock-qualification-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    )
    console.print(
        f"[bold blue]Qualifying {len(snapshot.constituents)} S&P 500 stocks...[/bold blue]"
    )
    result = StockQualificationPipeline().qualify(
        snapshot,
        model_name=model,
        training_start=start,
    )
    result.write_json(Path(report_path))
    result.write_csv(Path(report_path).with_suffix(".csv"))
    console.print(
        f"[green]Approved {len(result.approved_symbols)} of {len(result.results)} stocks[/green]"
    )
    console.print(f"JSON: {report_path}")
    console.print(f"CSV:  {Path(report_path).with_suffix('.csv')}")


@stocks.command("train-approved")
@click.option(
    "--report",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def train_approved(report) -> None:
    """Train final artifacts for every stock approved by a qualification report."""
    from tradex.stocks import QualificationReport, train_approved_stocks

    qualification = QualificationReport.read_json(report)
    outcomes = train_approved_stocks(qualification)
    failures = {symbol: value for symbol, value in outcomes.items() if value.startswith("ERROR:")}
    for symbol, outcome in outcomes.items():
        color = "red" if outcome.startswith("ERROR:") else "green"
        console.print(f"[{color}]{symbol}: {outcome}[/{color}]")
    console.print(
        f"Trained {len(outcomes) - len(failures)} of "
        f"{len(qualification.approved_symbols)} approved stocks"
    )


@cli.group()
def crypto() -> None:
    """Screen and train daily Kraken USD spot models."""


@crypto.command("refresh-universe")
@click.option(
    "--output",
    type=click.Path(path_type=Path),
    default=None,
    help="Snapshot JSON path (default: packaged Kraken USD snapshot)",
)
def refresh_crypto_universe(output) -> None:
    """Refresh the versioned Kraken USD spot market snapshot."""
    from tradex.crypto.universe import DEFAULT_SNAPSHOT_PATH, refresh_universe

    path = output or DEFAULT_SNAPSHOT_PATH
    universe = refresh_universe(path)
    console.print(f"[green]Saved {len(universe.markets)} markets to {path}[/green]")


@crypto.command("qualify")
@click.option(
    "--model",
    default="xgboost",
    show_default=True,
    type=click.Choice(["xgboost", "random_forest"]),
)
@click.option(
    "--report",
    type=click.Path(path_type=Path),
    default=None,
    help="Output JSON report path",
)
@click.option(
    "--universe",
    "universe_path",
    type=click.Path(path_type=Path),
    default=None,
    help="Universe snapshot path",
)
def qualify_crypto(model: str, report, universe_path) -> None:
    """Screen Kraken USD spot markets and run walk-forward qualification."""
    from datetime import UTC, datetime

    from tradex.config.settings import ROOT
    from tradex.crypto import CryptoQualificationPipeline
    from tradex.crypto.universe import DEFAULT_SNAPSHOT_PATH, load_universe

    snapshot = load_universe(universe_path or DEFAULT_SNAPSHOT_PATH)
    report_path = report or (
        ROOT / "reports" / f"crypto-qualification-{datetime.now(UTC):%Y%m%dT%H%M%SZ}.json"
    )
    console.print(
        f"[bold blue]Qualifying {len(snapshot.markets)} Kraken USD spot markets...[/bold blue]"
    )
    result = CryptoQualificationPipeline().qualify(snapshot, model_name=model)
    result.write_json(Path(report_path))
    result.write_csv(Path(report_path).with_suffix(".csv"))
    console.print(
        f"[green]Approved {len(result.approved_symbols)} of {len(result.results)} markets[/green]"
    )
    console.print(f"JSON: {report_path}")
    console.print(f"CSV:  {Path(report_path).with_suffix('.csv')}")


@crypto.command("train-approved")
@click.option(
    "--report",
    required=True,
    type=click.Path(exists=True, dir_okay=False, path_type=Path),
)
def train_approved_crypto_cmd(report) -> None:
    """Train final artifacts for approved Kraken crypto markets."""
    from tradex.crypto import CryptoQualificationReport, train_approved_crypto

    qualification = CryptoQualificationReport.read_json(report)
    outcomes = train_approved_crypto(qualification)
    failures = {symbol: value for symbol, value in outcomes.items() if value.startswith("ERROR:")}
    for symbol, outcome in outcomes.items():
        color = "red" if outcome.startswith("ERROR:") else "green"
        console.print(f"[{color}]{symbol}: {outcome}[/{color}]")
    console.print(
        f"Trained {len(outcomes) - len(failures)} of "
        f"{len(qualification.approved_symbols)} approved crypto markets"
    )


@cli.group()
def drill() -> None:
    """Run the isolated one-day automated paper-trading drill."""


@drill.command("prepare")
@click.option("--date", "session_date", required=True, type=click.DateTime(["%Y-%m-%d"]))
@click.option(
    "--force",
    is_flag=True,
    help="Re-prepare an existing drill only when it has no fills.",
)
def prepare_drill(session_date, force: bool) -> None:
    """Fetch daily data, validate models, and prepare drill artifacts."""
    from tradex.drill.engine import default_engine

    engine = default_engine()
    try:
        drill_id = engine.prepare(session_date.date(), force=force)
    except ValueError as exc:
        raise click.ClickException(str(exc)) from exc
    console.print(f"[green]Prepared drill {drill_id} for {session_date:%Y-%m-%d}[/green]")


@drill.command("run")
@click.option("--date", "session_date", required=True, type=click.DateTime(["%Y-%m-%d"]))
def run_drill(session_date) -> None:
    """Run the blocking five-minute drill scheduler for one session."""
    from tradex.drill.engine import default_engine

    engine = default_engine()
    console.print(
        f"[bold blue]Starting internal paper drill for {session_date:%Y-%m-%d}[/bold blue]"
    )
    drill_id = engine.run_live(session_date.date())
    console.print(f"[green]Drill {drill_id} scheduler finished[/green]")


@drill.command("status")
def drill_status_cmd() -> None:
    """Print the latest drill state."""
    from tradex.drill.engine import default_engine

    engine = default_engine()
    drill_id = engine.store.latest_drill_id()
    if drill_id is None:
        raise click.ClickException("No drill has been created")
    console.print_json(data=engine.status(drill_id))


@drill.command("halt")
@click.option("--yes", is_flag=True, help="Skip the interactive confirmation")
def halt_drill_cmd(yes: bool) -> None:
    """Emergency-stop all new drill activity."""
    from tradex.drill.engine import default_engine

    if not yes and not click.confirm("Halt the latest automated drill?"):
        raise click.Abort()
    engine = default_engine()
    drill_id = engine.store.latest_drill_id()
    if drill_id is None:
        raise click.ClickException("No drill has been created")
    engine.halt(drill_id)
    console.print(f"[yellow]Drill {drill_id} halted[/yellow]")


@drill.command("report")
@click.option(
    "--format",
    "output_format",
    type=click.Choice(["json", "html"]),
    default="json",
    show_default=True,
)
@click.option("--output", type=click.Path(path_type=Path), default=None)
def drill_report_cmd(output_format: str, output: Path | None) -> None:
    """Generate a report for the latest drill."""
    from tradex.config.settings import settings
    from tradex.drill.engine import default_engine
    from tradex.drill.report import build_report, write_report

    engine = default_engine()
    drill_id = engine.store.latest_drill_id()
    if drill_id is None:
        raise click.ClickException("No drill has been created")
    drill_record = engine.store.drill(drill_id)
    destination = output or (
        Path(settings.drill_data_dir)
        / "reports"
        / f"drill-{drill_record['session_date']}.{output_format}"
    )
    path = write_report(build_report(engine.store, drill_id), destination, output_format)
    console.print(f"[green]Saved drill report to {path}[/green]")


@cli.command()
@click.option("--side", required=True, type=click.Choice(["BUY", "SELL"], case_sensitive=False))
@click.option("--asset", required=True, help="Symbol such as AAPL, EURUSD, or BTC")
@click.option("--quantity", required=True, type=click.FloatRange(min=0, min_open=True))
@click.option(
    "--asset-type",
    default="STOCK",
    show_default=True,
    type=click.Choice(["STOCK", "FOREX", "CRYPTO"], case_sensitive=False),
)
@click.option(
    "--order-type",
    default="MARKET",
    show_default=True,
    type=click.Choice(["MARKET", "LIMIT"], case_sensitive=False),
)
@click.option("--limit-price", type=click.FloatRange(min=0, min_open=True))
@click.option("--exchange", default=None, help="IBKR exchange override for stocks or forex")
@click.option("--currency", default="USD", show_default=True)
@click.option(
    "--time-in-force",
    default="DAY",
    show_default=True,
    type=click.Choice(["DAY", "GTC"], case_sensitive=False),
)
@click.option("--outside-rth", is_flag=True, help="Allow execution outside regular trading hours")
@click.option("--platform", default=None, help="Override the default platform, e.g. ibkr or kraken")
@click.option(
    "--submit",
    is_flag=True,
    help="Transmit the order to the broker. Without this flag, only preview it.",
)
def trade(
    side: str,
    asset: str,
    quantity: float,
    asset_type: str,
    order_type: str,
    limit_price: float | None,
    exchange: str | None,
    currency: str,
    time_in_force: str,
    outside_rth: bool,
    platform: str | None,
    submit: bool,
) -> None:
    """Preview or submit an order through a registered trading platform."""
    from tradex.execution import OrderRequest, platforms

    try:
        request = OrderRequest(
            symbol=asset,
            side=side,
            quantity=quantity,
            asset_type=asset_type,
            order_type=order_type,
            limit_price=limit_price,
            exchange=exchange,
            currency=currency,
            time_in_force=time_in_force,
            outside_rth=outside_rth,
        )
    except ValueError as exc:
        raise click.BadParameter(str(exc)) from exc

    try:
        broker = platforms.create(request, platform)
        preview = broker.preview(request)
    except ValueError as exc:
        raise click.BadParameter(str(exc), param_hint="--platform") from exc

    console.print(
        f"[bold]{request.side}[/bold] {request.quantity:g} {request.symbol} "
        f"as a {request.order_type} order on "
        f"{preview.platform.upper()} ({preview.venue}: {preview.symbol})"
    )

    if not submit:
        console.print("[yellow]Preview only. Add --submit to transmit this order.[/yellow]")
        return

    try:
        result = broker.submit(request)
    except Exception as exc:
        raise click.ClickException(f"Order failed: {exc}") from exc
    finally:
        broker.close()

    console.print(
        f"[green]{result.broker} order {result.order_id} submitted[/green]: "
        f"{result.status}, filled {result.filled:g}, remaining {result.remaining:g}"
    )


if __name__ == "__main__":
    cli()
