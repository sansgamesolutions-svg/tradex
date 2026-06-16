from __future__ import annotations

import math
from collections.abc import Callable
from datetime import UTC, date, datetime, timedelta
from pathlib import Path

from apscheduler.schedulers.blocking import BlockingScheduler

from tradex.config.settings import settings
from tradex.drill.market import DrillMarketData, LiveDrillMarketData
from tradex.drill.report import build_report, write_report
from tradex.drill.signals import DrillSignalService
from tradex.drill.store import DrillStore
from tradex.drill.types import (
    CostModel,
    DrillConfig,
    PortfolioKind,
    PortfolioView,
    PriceQuote,
    RiskDecision,
)
from tradex.strategy.schema import StrategyConfig

Clock = Callable[[], datetime]


class DrillEngine:
    """Restart-safe one-session paper trading coordinator."""

    def __init__(
        self,
        store: DrillStore | None = None,
        market_data: DrillMarketData | None = None,
        *,
        clock: Clock | None = None,
        strategy: StrategyConfig | None = None,
    ) -> None:
        data_dir = Path(settings.drill_data_dir)
        self.store = store or DrillStore(data_dir / "tradex-drill.sqlite3")
        self.market_data = market_data or LiveDrillMarketData()
        self.clock = clock or (lambda: datetime.now(UTC))
        self.signals = DrillSignalService(self.store, self.market_data)
        self._strategy = strategy or StrategyConfig.default()

    def prepare(self, session_date: date, *, force: bool = False) -> int:
        config = DrillConfig.from_settings(session_date)
        drill_id = self.store.create_drill(config)
        drill = self.store.drill(drill_id)
        if force:
            self.store.reset_for_preparation(drill_id, config)
            drill = self.store.drill(drill_id)
        if drill["status"] in {"PREPARED", "RUNNING", "COMPLETED"}:
            return drill_id
        self.store.record_event(drill_id, "OPERATIONS", "Model preparation started")
        self.signals.prepare(drill_id, config)
        self.store.set_status(drill_id, "PREPARED")
        self.store.record_event(drill_id, "OPERATIONS", "Model preparation completed")
        return drill_id

    def halt(self, drill_id: int, reason: str = "manual emergency halt") -> None:
        self.store.set_status(drill_id, "HALTED", reason)
        for kind in ("STOCK", "CRYPTO"):
            self.store.set_portfolio_halted(drill_id, kind, True)
        self.store.record_event(drill_id, "OPERATIONS", reason, level="WARNING")

    def run_cycle(self, drill_id: int, now: datetime | None = None) -> None:
        current = (now or self.clock()).astimezone(UTC)
        drill = self.store.drill(drill_id)
        if drill["status"] in {"HALTED", "COMPLETED", "FAILED"}:
            return
        config = self._config(drill)
        local = current.astimezone(config.opens_at.tzinfo)
        if local < config.opens_at:
            return
        if drill["status"] == "PREPARED":
            self.store.set_status(drill_id, "RUNNING")

        quotes = self._capture_quotes(drill_id, config, current)
        self._fill_pending_orders(drill_id, config, quotes, current)
        self._evaluate_exits(drill_id, config, quotes, current)

        if config.entries_at <= local <= config.entry_retry_deadline:
            self._evaluate_entries(drill_id, config, quotes, current)
        elif local > config.entry_retry_deadline:
            self._expire_unresolved_entries(drill_id, current)

        if local >= config.force_close_at:
            self._force_close(drill_id, config, current)

        self._mark_portfolios(drill_id, config, current)
        if local >= config.ends_at:
            self.finalize(drill_id)

    def run_live(self, session_date: date) -> int:
        drill_id = self.prepare(session_date)
        config = DrillConfig.from_settings(session_date)
        now = self.clock().astimezone(config.opens_at.tzinfo)
        if now >= config.ends_at:
            self.run_cycle(drill_id, now)
            return drill_id

        scheduler = BlockingScheduler(timezone=config.opens_at.tzinfo)
        run_at = config.opens_at
        while run_at <= config.ends_at:
            if run_at >= now:
                scheduler.add_job(
                    self.run_cycle,
                    "date",
                    run_date=run_at,
                    args=(drill_id, run_at),
                    id=f"drill-{drill_id}-{run_at:%H%M}",
                    misfire_grace_time=240,
                )
            run_at += timedelta(minutes=5)
        scheduler.add_job(
            scheduler.shutdown,
            "date",
            run_date=config.ends_at + timedelta(seconds=1),
            kwargs={"wait": False},
            id=f"drill-{drill_id}-shutdown",
        )
        self.store.record_event(drill_id, "OPERATIONS", "Live drill scheduler started")
        try:
            scheduler.start()
        finally:
            self.market_data.close()
        return drill_id

    def finalize(self, drill_id: int) -> None:
        drill = self.store.drill(drill_id)
        if drill["status"] == "COMPLETED":
            return
        self.store.set_status(drill_id, "COMPLETED")
        report = build_report(self.store, drill_id)
        base = Path(settings.drill_data_dir) / "reports" / f"drill-{drill['session_date']}"
        write_report(report, base.with_suffix(".json"), "json")
        write_report(report, base.with_suffix(".html"), "html")
        self.store.record_event(drill_id, "OPERATIONS", "Final drill report generated")

    def status(self, drill_id: int) -> dict:
        drill = self.store.drill(drill_id)
        config = self._config(drill)
        views = [self._portfolio_view(drill_id, kind, config) for kind in ("STOCK", "CRYPTO")]
        return {
            "drill": drill,
            "portfolios": [view.__dict__ for view in views],
            "positions": self.store.open_positions(drill_id),
            "signals": self.store.table("signals", drill_id),
            "orders": self.store.table("orders", drill_id),
            "events": self.store.table("events", drill_id)[-50:],
            "equity_curve": self.store.table("equity_points", drill_id),
            "preparations": self.store.table("model_preparations", drill_id),
            "prices": self.store.table("prices", drill_id)[-50:],
            "entry_states": self.store.entry_states(drill_id),
            "symbol_health": self.store.symbol_health(drill_id),
        }

    def _capture_quotes(
        self,
        drill_id: int,
        config: DrillConfig,
        now: datetime,
    ) -> dict[tuple[str, str], PriceQuote]:
        quotes: dict[tuple[str, str], PriceQuote] = {}
        for kind, symbols in (
            ("STOCK", config.stock_symbols),
            ("CRYPTO", config.crypto_symbols),
        ):
            if not symbols:
                self.store.update_data_failures(drill_id, kind, 0)
                continue
            valid = 0
            health = {
                item["symbol"]: item
                for item in self.store.symbol_health(drill_id)
                if item["portfolio"] == kind
            }
            for symbol in symbols:
                if health.get(symbol, {}).get("disabled"):
                    continue
                try:
                    quote = self.market_data.fetch_quote(kind, symbol, now)
                    self._validate_quote(quote, config, now)
                    self.store.record_price(drill_id, quote)
                    self.store.record_symbol_success(drill_id, kind, symbol)
                    quotes[(kind, symbol)] = quote
                    valid += 1
                except Exception as exc:
                    failures = self.store.record_symbol_failure(
                        drill_id, kind, symbol, str(exc), config.max_symbol_failures
                    )
                    self.store.record_event(
                        drill_id,
                        "DATA",
                        f"{kind} {symbol} quote failed",
                        level="WARNING",
                        details={"error": str(exc), "consecutive_failures": failures},
                        occurred_at=now,
                    )
            portfolio = self.store.portfolio(drill_id, kind)
            coverage = valid / len(symbols)
            consecutive = (
                int(portfolio["data_failures"]) + 1 if coverage < config.min_quote_coverage else 0
            )
            self.store.update_data_failures(drill_id, kind, consecutive)
            if consecutive >= 3:
                self.store.set_portfolio_halted(drill_id, kind, True)
                self.store.record_event(
                    drill_id,
                    "RISK",
                    f"{kind} entries halted after repeated low quote coverage",
                    level="WARNING",
                    details={"coverage": coverage},
                    occurred_at=now,
                )
        return quotes

    def _evaluate_entries(
        self,
        drill_id: int,
        config: DrillConfig,
        quotes: dict[tuple[str, str], PriceQuote],
        now: datetime,
    ) -> None:
        for kind, symbols in (
            ("STOCK", config.stock_symbols),
            ("CRYPTO", config.crypto_symbols),
        ):
            decisions = []
            pending = {
                item["symbol"]
                for item in self.store.entry_states(drill_id, "PENDING")
                if item["portfolio"] == kind
            }
            for symbol in symbols:
                if symbol not in pending:
                    continue
                quote = quotes.get((kind, symbol))
                if quote is None:
                    self._entry_failure(
                        drill_id, config, kind, symbol, "fresh quote unavailable", now
                    )
                    continue
                try:
                    decision = self.signals.decide(drill_id, config, kind, symbol, now)
                except Exception as exc:
                    self.store.record_event(
                        drill_id,
                        "SIGNAL",
                        f"{kind} {symbol} signal failed",
                        level="WARNING",
                        details={"error": str(exc)},
                        occurred_at=now,
                    )
                    self._entry_failure(
                        drill_id, config, kind, symbol, f"signal failed: {exc}", now
                    )
                    continue
                self.store.record_signal(drill_id, decision)
                if decision.signal != "BUY":
                    self.store.set_entry_state(drill_id, kind, symbol, "NO_TRADE", decision.signal)
                decisions.append(decision)

            ranked = sorted(
                (item for item in decisions if item.signal == "BUY"),
                key=lambda item: (item.fused_probability, item.confidence),
                reverse=True,
            )
            for decision in ranked:
                quote = quotes.get((kind, decision.symbol))
                risk = self._entry_risk(
                    drill_id,
                    config,
                    decision.portfolio,
                    decision.symbol,
                    quote,
                    now,
                    confidence=decision.confidence,
                )
                if not risk.accepted:
                    self.store.record_event(
                        drill_id,
                        "RISK",
                        f"{kind} {decision.symbol} entry rejected: {risk.reason}",
                        details={"estimated_all_in_cost": risk.estimated_all_in_cost},
                        occurred_at=now,
                    )
                    self.store.set_entry_state(
                        drill_id, kind, decision.symbol, "REJECTED", risk.reason
                    )
                    continue
                self.store.create_order(
                    drill_id,
                    kind,
                    decision.symbol,
                    "BUY",
                    risk.quantity,
                    "ENTRY_SIGNAL",
                    f"{drill_id}:{kind}:{decision.symbol}:ENTRY",
                    now,
                )
                self.store.set_entry_state(
                    drill_id, kind, decision.symbol, "ORDER_CREATED", "accepted"
                )

    def _entry_risk(
        self,
        drill_id: int,
        config: DrillConfig,
        kind: PortfolioKind,
        symbol: str,
        quote: PriceQuote | None,
        now: datetime,
        *,
        confidence: float = 0.0,
    ) -> RiskDecision:
        portfolio = self.store.portfolio(drill_id, kind)
        if portfolio["halted"]:
            return RiskDecision(False, "portfolio is halted")
        if quote is None:
            return RiskDecision(False, "no current price")
        try:
            self._validate_quote(quote, config, now)
        except ValueError as exc:
            return RiskDecision(False, str(exc))
        open_positions = self.store.open_positions(drill_id, kind)
        pending_entries = [
            order
            for order in self.store.pending_orders(drill_id)
            if order["portfolio"] == kind and order["side"] == "BUY"
        ]
        risk = self._strategy.risk
        if len(open_positions) + len(pending_entries) >= risk.max_open_positions:
            return RiskDecision(False, "maximum open positions reached")
        if any(position["symbol"] == symbol for position in open_positions):
            return RiskDecision(False, "symbol already has an open position")
        if self.store.symbol_was_closed(drill_id, kind, symbol):
            return RiskDecision(False, "re-entry is disabled")

        scale = self._strategy.position_scale(confidence)
        if scale == 0.0:
            return RiskDecision(False, "confidence below minimum threshold")
        effective_cost = risk.max_position_cost * scale
        costs = self._costs(config, kind)
        quantity = (effective_cost - costs.fixed_fee) / (
            quote.price * (1 + costs.slippage_rate) * (1 + costs.fee_rate)
        )
        quantity = max(math.floor(quantity * 100_000_000) / 100_000_000, 0.0)
        fill_price = costs.fill_price(quote.price, "BUY")
        all_in = fill_price * quantity + costs.fee(fill_price * quantity)
        if quantity <= 0 or all_in > float(portfolio["cash"]) + 1e-9:
            return RiskDecision(False, "insufficient cash", quantity, all_in)
        if all_in > effective_cost + 1e-6:
            return RiskDecision(False, "position cap exceeded", quantity, all_in)
        return RiskDecision(True, "accepted", quantity, all_in)

    def _evaluate_exits(
        self,
        drill_id: int,
        config: DrillConfig,
        quotes: dict[tuple[str, str], PriceQuote],
        now: datetime,
    ) -> None:
        for position in self.store.open_positions(drill_id):
            quote = quotes.get((position["portfolio"], position["symbol"]))
            if quote is None:
                continue
            reason = ""
            if quote.price <= position["stop_price"]:
                reason = "STOP_LOSS"
            elif quote.price >= position["take_profit_price"]:
                reason = "TAKE_PROFIT"
            if reason:
                self.store.create_order(
                    drill_id,
                    position["portfolio"],
                    position["symbol"],
                    "SELL",
                    position["quantity"],
                    reason,
                    f"{drill_id}:{position['portfolio']}:{position['symbol']}:{reason}",
                    now,
                )

    def _force_close(self, drill_id: int, config: DrillConfig, now: datetime) -> None:
        for position in self.store.open_positions(drill_id):
            self.store.create_order(
                drill_id,
                position["portfolio"],
                position["symbol"],
                "SELL",
                position["quantity"],
                "SESSION_CLOSE",
                f"{drill_id}:{position['portfolio']}:{position['symbol']}:SESSION_CLOSE",
                now,
            )

    def _fill_pending_orders(
        self,
        drill_id: int,
        config: DrillConfig,
        quotes: dict[tuple[str, str], PriceQuote],
        now: datetime,
    ) -> None:
        for order in self.store.pending_orders(drill_id):
            quote = quotes.get((order["portfolio"], order["symbol"]))
            if quote is None:
                continue
            created_at = datetime.fromisoformat(order["created_at"]).astimezone(UTC)
            if quote.period_end.astimezone(UTC) <= created_at:
                self.store.record_event(
                    drill_id,
                    "EXECUTION",
                    f"{order['portfolio']} {order['symbol']} simulated fill deferred",
                    details={"reason": "no completed bar after order creation"},
                    occurred_at=now,
                )
                continue
            try:
                self._validate_quote(quote, config, now)
                self._apply_fill(order, config, quote, quote.period_end)
            except Exception as exc:
                self.store.record_event(
                    drill_id,
                    "EXECUTION",
                    f"{order['portfolio']} {order['symbol']} simulated fill deferred",
                    level="WARNING",
                    details={"error": str(exc)},
                    occurred_at=now,
                )

    def _apply_fill(
        self,
        order: dict,
        config: DrillConfig,
        quote: PriceQuote,
        filled_at: datetime,
    ) -> None:
        if quote.period_end.astimezone(UTC) <= datetime.fromisoformat(
            order["created_at"]
        ).astimezone(UTC):
            return
        costs = self._costs(config, order["portfolio"])
        fill_price = costs.fill_price(quote.price, order["side"])
        notional = fill_price * order["quantity"]
        fee = costs.fee(notional)
        slippage = abs(fill_price - quote.price) * order["quantity"]
        if order["side"] == "BUY":
            self.store.apply_buy_fill(
                order,
                market_price=quote.price,
                fill_price=fill_price,
                fee=fee,
                slippage=slippage,
                stop_price=fill_price * (1 - self._strategy.risk.stop_loss_rate),
                take_profit_price=fill_price * (1 + self._strategy.risk.take_profit_rate),
                filled_at=filled_at,
            )
        else:
            position = next(
                (
                    item
                    for item in self.store.open_positions(order["drill_id"], order["portfolio"])
                    if item["symbol"] == order["symbol"]
                ),
                None,
            )
            if position is None:
                return
            self.store.apply_sell_fill(
                order,
                position,
                market_price=quote.price,
                fill_price=fill_price,
                fee=fee,
                slippage=slippage,
                filled_at=filled_at,
            )

    def _mark_portfolios(
        self,
        drill_id: int,
        config: DrillConfig,
        now: datetime,
    ) -> None:
        for kind in ("STOCK", "CRYPTO"):
            view = self._portfolio_view(drill_id, kind, config)
            self.store.record_equity(drill_id, kind, view.equity, view.cash, now)
            portfolio = self.store.portfolio(drill_id, kind)
            drawdown = (view.equity - portfolio["peak_equity"]) / portfolio["peak_equity"]
            risk = self._strategy.risk
            if drawdown <= -risk.max_drawdown_rate and not portfolio["halted"]:
                self.store.set_portfolio_halted(drill_id, kind, True)
                self.store.record_event(
                    drill_id,
                    "RISK",
                    f"{kind} entries halted at {drawdown:.2%} drawdown",
                    level="WARNING",
                    occurred_at=now,
                )
            session_loss_rate = (view.equity - config.initial_capital) / config.initial_capital
            if session_loss_rate <= -risk.daily_loss_limit_rate and not portfolio["halted"]:
                self.store.set_portfolio_halted(drill_id, kind, True)
                self.store.record_event(
                    drill_id,
                    "RISK",
                    f"{kind} entries halted: daily loss limit reached ({session_loss_rate:.2%})",
                    level="WARNING",
                    occurred_at=now,
                )

    def _portfolio_view(
        self,
        drill_id: int,
        kind: PortfolioKind,
        config: DrillConfig,
    ) -> PortfolioView:
        portfolio = self.store.portfolio(drill_id, kind)
        market_value = 0.0
        unrealized = 0.0
        positions = self.store.open_positions(drill_id, kind)
        for position in positions:
            latest = self.store.latest_price(drill_id, kind, position["symbol"])
            price = float(latest["price"]) if latest else float(position["entry_price"])
            market_value += price * position["quantity"]
            unrealized += (price - position["entry_price"]) * position["quantity"]
        equity = float(portfolio["cash"]) + market_value
        return PortfolioView(
            kind=kind,
            cash=float(portfolio["cash"]),
            equity=equity,
            realized_pnl=float(portfolio["realized_pnl"]),
            unrealized_pnl=unrealized,
            fees=float(portfolio["fees"]),
            slippage=float(portfolio["slippage"]),
            open_positions=len(positions),
            halted=bool(portfolio["halted"]),
            data_failures=int(portfolio["data_failures"]),
        )

    @staticmethod
    def _costs(config: DrillConfig, kind: PortfolioKind) -> CostModel:
        if kind == "STOCK":
            return CostModel(
                slippage_rate=config.stock_slippage_rate,
                fixed_fee=config.stock_fixed_fee,
            )
        return CostModel(
            slippage_rate=config.crypto_slippage_rate,
            fee_rate=config.crypto_fee_rate,
        )

    def _entry_failure(
        self,
        drill_id: int,
        config: DrillConfig,
        kind: PortfolioKind,
        symbol: str,
        reason: str,
        now: datetime,
    ) -> None:
        failures = self.store.record_entry_failure(
            drill_id, kind, symbol, reason, config.max_symbol_failures
        )
        if failures >= config.max_symbol_failures:
            self.store.record_event(
                drill_id,
                "SIGNAL",
                f"{kind} {symbol} entry evaluation expired after repeated failures",
                level="WARNING",
                details={"reason": reason, "failures": failures},
                occurred_at=now,
            )

    def _expire_unresolved_entries(self, drill_id: int, now: datetime) -> None:
        for item in self.store.entry_states(drill_id, "PENDING"):
            self.store.set_entry_state(
                drill_id,
                item["portfolio"],
                item["symbol"],
                "EXPIRED",
                "entry retry deadline passed",
            )
            self.store.record_event(
                drill_id,
                "SIGNAL",
                f"{item['portfolio']} {item['symbol']} entry evaluation expired",
                occurred_at=now,
            )

    @staticmethod
    def _validate_quote(quote: PriceQuote, config: DrillConfig, now: datetime) -> None:
        if not math.isfinite(quote.price) or quote.price <= 0:
            raise ValueError("price must be finite and positive")
        source = quote.source_timestamp.astimezone(UTC)
        current = now.astimezone(UTC)
        if source - current > timedelta(seconds=config.max_future_seconds):
            raise ValueError("price timestamp is excessively future-dated")
        if current - source > timedelta(minutes=config.max_price_age_minutes):
            raise ValueError("price is stale")
        if quote.period_start >= quote.period_end:
            raise ValueError("quote period is invalid")
        if quote.period_end.astimezone(UTC) > current:
            raise ValueError("quote bar is not completed")

    @staticmethod
    def _config(drill: dict) -> DrillConfig:
        session_date = date.fromisoformat(drill["session_date"])
        payload = DrillConfig.from_settings(session_date).to_dict()
        payload.update(drill["config"])
        payload["session_date"] = date.fromisoformat(payload["session_date"])
        payload["stock_symbols"] = tuple(payload["stock_symbols"])
        payload["crypto_symbols"] = tuple(payload["crypto_symbols"])
        return DrillConfig(**payload)


def default_engine():
    from tradex.auto.engine import default_engine as default_auto_engine

    return default_auto_engine()
