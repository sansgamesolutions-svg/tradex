from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd
from rich.console import Console
from rich.table import Table

from tradex.config.settings import settings
from tradex.signals.combiner import SignalCombiner

console = Console()


@dataclass
class BacktestResults:
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    n_trades: int
    equity_curve: pd.Series


class Backtester:
    def __init__(
        self,
        model_name: str = "xgboost",
        initial_capital: float = 10_000.0,
        fee: float = 0.001,
    ):
        self.model_name = model_name
        self.initial_capital = initial_capital
        self.fee = fee  # round-trip cost applied at entry and exit

    def run(
        self, features: pd.DataFrame, raw_df: pd.DataFrame | None = None
    ) -> BacktestResults:
        combiner = SignalCombiner(self.model_name)
        equity = self.initial_capital
        equity_curve: list[float] = []
        in_position = False
        entry_price = 0.0
        wins = total_trades = 0

        prices: pd.Series | None = raw_df["close"] if raw_df is not None else None

        for i in range(settings.lookback_periods, len(features)):
            window = features.iloc[:i]
            raw_window = raw_df.iloc[:i] if raw_df is not None else None
            signal = combiner.predict(window, raw_window)

            if prices is not None:
                price = prices.iloc[i]
                if signal == "BUY" and not in_position:
                    entry_price = price * (1 + self.fee)
                    in_position = True
                    total_trades += 1
                elif signal == "SELL" and in_position:
                    ret = (price * (1 - self.fee) - entry_price) / entry_price
                    equity *= 1 + ret
                    wins += int(ret > 0)
                    in_position = False

            equity_curve.append(equity)

        curve = pd.Series(equity_curve, index=features.index[settings.lookback_periods :])
        daily_returns = curve.pct_change().dropna()

        total_return = (equity - self.initial_capital) / self.initial_capital
        sharpe = (
            daily_returns.mean() / daily_returns.std() * np.sqrt(252)
            if daily_returns.std() > 0
            else 0.0
        )
        max_drawdown = float(((curve - curve.cummax()) / curve.cummax()).min())
        win_rate = wins / total_trades if total_trades > 0 else 0.0

        return BacktestResults(
            total_return=total_return,
            sharpe_ratio=sharpe,
            max_drawdown=max_drawdown,
            win_rate=win_rate,
            n_trades=total_trades,
            equity_curve=curve,
        )

    def print_report(self, results: BacktestResults) -> None:
        table = Table(title="Backtest Results")
        table.add_column("Metric", style="cyan")
        table.add_column("Value", style="magenta")
        table.add_row("Total Return", f"{results.total_return:.2%}")
        table.add_row("Sharpe Ratio", f"{results.sharpe_ratio:.2f}")
        table.add_row("Max Drawdown", f"{results.max_drawdown:.2%}")
        table.add_row("Win Rate", f"{results.win_rate:.2%}")
        table.add_row("# Trades", str(results.n_trades))
        console.print(table)
