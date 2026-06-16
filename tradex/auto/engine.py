from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path

from tradex.auto.broker import BrokerRouter
from tradex.auto.profiles import one_day_drill_profile
from tradex.auto.types import ExecutionMode, SchedulerHealth, TradingProfile
from tradex.config.settings import settings
from tradex.drill.engine import DrillEngine
from tradex.drill.market import DrillMarketData
from tradex.drill.report import build_report, write_report
from tradex.drill.store import DrillStore
from tradex.drill.types import EASTERN
from tradex.execution.models import OrderRequest


class AutoTradingEngine(DrillEngine):
    """Production-shaped automatic trading coordinator.

    V1 deliberately supports only simulated execution. The inherited drill
    engine supplies the proven market-data, signal, risk, and fill loop.
    """

    def __init__(
        self,
        profile: TradingProfile | None = None,
        store: DrillStore | None = None,
        market_data: DrillMarketData | None = None,
        *,
        clock=None,
    ) -> None:
        self.profile = profile or one_day_drill_profile()
        super().__init__(
            store=store,
            market_data=market_data,
            clock=clock,
            strategy=self.profile.strategy,
        )
        self.broker_router = BrokerRouter(self.profile.execution_mode)

    def prepare(self, session_date: date, *, force: bool = False) -> int:
        config = self.profile.to_drill_config(session_date)
        drill_id = self.store.create_drill(
            config,
            profile_name=self.profile.name,
            profile_version=self.profile.version,
            execution_mode=self.profile.execution_mode,
        )
        if self.profile.execution_mode != "SIMULATED":
            self._fail_closed(drill_id, self.profile.execution_mode)
            raise ValueError(
                f"Automatic trading execution mode {self.profile.execution_mode} is disabled in v1"
            )

        drill = self.store.drill(drill_id)
        if force:
            self.store.reset_for_preparation(
                drill_id,
                config,
                profile_name=self.profile.name,
                profile_version=self.profile.version,
                execution_mode=self.profile.execution_mode,
            )
            drill = self.store.drill(drill_id)
        if drill["status"] in {"PREPARED", "RUNNING", "COMPLETED", "COMPLETED_NO_RUN"}:
            return drill_id
        if drill["status"] in {"EXPIRED", "HALTED", "FAILED"} and not force:
            return drill_id

        self.store.record_event(drill_id, "OPERATIONS", "Model preparation started")
        self.signals.prepare(drill_id, config)
        self.store.set_status(drill_id, "PREPARED")
        self.store.record_event(drill_id, "OPERATIONS", "Model preparation completed")
        return drill_id

    def run_cycle(self, drill_id: int, now: datetime | None = None) -> None:
        current = (now or self.clock()).astimezone(UTC)
        drill = self.store.drill(drill_id)
        if self._is_unstarted_past_session(drill, current):
            self._complete_no_run(drill_id, current, "session ended before automation started")
            return
        self.store.record_cycle(drill_id, current)
        super().run_cycle(drill_id, current)

    def run_live(self, session_date: date) -> int:
        drill_id = self.prepare(session_date)
        config = self.profile.to_drill_config(session_date)
        now = self.clock().astimezone(config.opens_at.tzinfo)
        if now >= config.ends_at:
            drill = self.store.drill(drill_id)
            if self._has_no_activity(drill_id) and drill["status"] in {"CREATED", "PREPARED"}:
                self._complete_no_run(
                    drill_id,
                    now.astimezone(UTC),
                    "session ended before automation started",
                )
                return drill_id
        return super().run_live(session_date)

    def status(self, drill_id: int) -> dict:
        payload = super().status(drill_id)
        drill = payload["drill"]
        payload["profile"] = {
            "name": drill.get("profile_name", self.profile.name),
            "version": drill.get("profile_version", self.profile.version),
            "execution_mode": drill.get("execution_mode", self.profile.execution_mode),
        }
        payload["scheduler_health"] = self.scheduler_health(drill_id).__dict__
        payload["automation"] = {
            "supported_execution_modes": ["SIMULATED"],
            "broker_execution_enabled": False,
            "expired_reason": drill.get("expired_reason", ""),
        }
        return payload

    def active_run_id(self, now: datetime | None = None) -> int | None:
        current = (now or self.clock()).astimezone(UTC)
        today = current.astimezone(EASTERN).date().isoformat()
        return self.store.next_actionable_drill_id(today) or self.store.latest_drill_id()

    def scheduler_health(self, drill_id: int) -> SchedulerHealth:
        drill = self.store.drill(drill_id)
        config = self._config(drill)
        now = self.clock().astimezone(config.opens_at.tzinfo)
        if now < config.opens_at:
            phase = "PRE_MARKET"
        elif now <= config.ends_at:
            phase = "OPEN"
        else:
            phase = "CLOSED"
        return SchedulerHealth(
            running=drill["status"] == "RUNNING",
            scheduler_heartbeat_at=drill.get("scheduler_heartbeat_at"),
            last_cycle_at=drill.get("last_cycle_at"),
            market_phase=phase,
        )

    def assert_route_supported(self, request: OrderRequest) -> None:
        broker = self.broker_router.create(request)
        broker.preview(request)

    def _fail_closed(self, drill_id: int, mode: ExecutionMode) -> None:
        self.store.record_event(
            drill_id,
            "EXECUTION",
            f"Automatic broker execution mode {mode} is disabled",
            level="ERROR",
            details={"execution_mode": mode},
        )
        self.store.set_status(drill_id, "FAILED", f"execution mode {mode} disabled")

    def _is_unstarted_past_session(self, drill: dict, now: datetime) -> bool:
        if drill["status"] not in {"CREATED", "PREPARED"}:
            return False
        config = self._config(drill)
        return now.astimezone(config.ends_at.tzinfo) > config.ends_at and self._has_no_activity(
            int(drill["id"])
        )

    def _has_no_activity(self, drill_id: int) -> bool:
        return not any(
            (
                self.store.table("signals", drill_id),
                self.store.table("orders", drill_id),
                self.store.table("fills", drill_id),
                self.store.table("equity_points", drill_id),
            )
        )

    def _complete_no_run(self, drill_id: int, now: datetime, reason: str) -> None:
        self.store.set_expired(drill_id, "COMPLETED_NO_RUN", reason)
        self.store.record_event(
            drill_id,
            "OPERATIONS",
            "Automation session completed without running",
            level="WARNING",
            details={"reason": reason},
            occurred_at=now,
        )
        report = build_report(self.store, drill_id)
        drill = self.store.drill(drill_id)
        base = Path(settings.drill_data_dir) / "reports" / f"drill-{drill['session_date']}"
        write_report(report, base.with_suffix(".json"), "json")
        write_report(report, base.with_suffix(".html"), "html")


def default_engine() -> AutoTradingEngine:
    return AutoTradingEngine()
