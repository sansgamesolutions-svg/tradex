import click
from rich.console import Console

console = Console()


@click.group()
@click.version_option()
def cli():
    """TradeX — multi-asset trade prediction CLI."""


@cli.command()
@click.option("--asset", required=True, help="Asset symbol, e.g. BTC, AAPL, EUR/USD")
@click.option("--timeframe", default="1d", show_default=True, help="Candle timeframe (1m/5m/15m/1h/4h/1d/1w)")
@click.option("--model", default="xgboost", show_default=True, type=click.Choice(["xgboost", "random_forest", "lstm"]))
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
@click.option("--model", default="xgboost", show_default=True, type=click.Choice(["xgboost", "random_forest", "lstm"]))
def backtest(asset: str, timeframe: str, start: str, end: str | None, model: str) -> None:
    """Run a historical backtest for an asset."""
    from tradex.data.fetcher import fetch
    from tradex.data.preprocessor import build_features
    from tradex.indicators.technical import add_indicators
    from tradex.backtester.engine import Backtester

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
@click.option("--model", default="xgboost", show_default=True, type=click.Choice(["xgboost", "random_forest", "lstm"]))
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


if __name__ == "__main__":
    cli()
