from __future__ import annotations

from datetime import UTC, datetime

from apscheduler.schedulers.asyncio import AsyncIOScheduler

from tradex.auto.engine import AutoTradingEngine, default_engine


class AutoTradingWorker:
    """FastAPI-hosted automation worker for the active paper run."""

    def __init__(self, engine: AutoTradingEngine | None = None) -> None:
        self.engine = engine or default_engine()
        self.scheduler = AsyncIOScheduler(timezone="America/New_York")

    @property
    def running(self) -> bool:
        return self.scheduler.running

    def start(self) -> None:
        if self.scheduler.running:
            return
        self.scheduler.add_job(
            self.tick,
            "interval",
            minutes=5,
            next_run_time=datetime.now(UTC),
            id="auto-trading-worker",
            replace_existing=True,
            misfire_grace_time=240,
        )
        self.scheduler.start()

    def stop(self) -> None:
        if self.scheduler.running:
            self.scheduler.shutdown(wait=False)

    def tick(self) -> None:
        drill_id = self.engine.active_run_id()
        if drill_id is None:
            return
        drill = self.engine.store.drill(drill_id)
        if drill["status"] in {"CREATED", "PREPARED", "RUNNING"}:
            self.engine.run_cycle(drill_id)

    def health(self) -> dict:
        drill_id = self.engine.active_run_id()
        active = self.engine.store.drill(drill_id) if drill_id is not None else None
        return {
            "running": self.running,
            "active_run_id": drill_id,
            "active_status": active["status"] if active else None,
            "now": datetime.now(UTC).isoformat(),
        }


worker = AutoTradingWorker()
