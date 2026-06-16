from __future__ import annotations

import json
import sqlite3
from collections.abc import Iterator
from contextlib import contextmanager
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from tradex.drill.types import DrillConfig, PriceQuote, SignalDecision


class DrillStore:
    """SQLite-backed source of truth for simulated drill state."""

    def __init__(self, path: Path) -> None:
        self.path = path
        self.path.parent.mkdir(parents=True, exist_ok=True)
        self._initialize()

    @contextmanager
    def connection(self) -> Iterator[sqlite3.Connection]:
        connection = sqlite3.connect(self.path, timeout=30)
        connection.row_factory = sqlite3.Row
        connection.execute("PRAGMA foreign_keys = ON")
        try:
            yield connection
            connection.commit()
        except Exception:
            connection.rollback()
            raise
        finally:
            connection.close()

    def _initialize(self) -> None:
        with self.connection() as db:
            db.executescript(
                """
                PRAGMA journal_mode = WAL;

                CREATE TABLE IF NOT EXISTS drills (
                    id INTEGER PRIMARY KEY,
                    session_date TEXT NOT NULL UNIQUE,
                    status TEXT NOT NULL,
                    config_json TEXT NOT NULL,
                    created_at TEXT NOT NULL,
                    updated_at TEXT NOT NULL,
                    halt_reason TEXT NOT NULL DEFAULT '',
                    profile_name TEXT NOT NULL DEFAULT 'one-day-drill',
                    profile_version TEXT NOT NULL DEFAULT '1.0',
                    execution_mode TEXT NOT NULL DEFAULT 'SIMULATED',
                    scheduler_heartbeat_at TEXT,
                    last_cycle_at TEXT,
                    expired_reason TEXT NOT NULL DEFAULT ''
                );

                CREATE TABLE IF NOT EXISTS portfolios (
                    drill_id INTEGER NOT NULL,
                    kind TEXT NOT NULL,
                    initial_capital REAL NOT NULL,
                    cash REAL NOT NULL,
                    realized_pnl REAL NOT NULL DEFAULT 0,
                    fees REAL NOT NULL DEFAULT 0,
                    slippage REAL NOT NULL DEFAULT 0,
                    peak_equity REAL NOT NULL,
                    halted INTEGER NOT NULL DEFAULT 0,
                    data_failures INTEGER NOT NULL DEFAULT 0,
                    PRIMARY KEY (drill_id, kind),
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );

                CREATE TABLE IF NOT EXISTS model_preparations (
                    drill_id INTEGER NOT NULL,
                    portfolio TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    approved INTEGER NOT NULL,
                    source TEXT NOT NULL,
                    artifact_path TEXT,
                    metrics_json TEXT NOT NULL,
                    reason TEXT NOT NULL,
                    prepared_at TEXT NOT NULL,
                    PRIMARY KEY (drill_id, portfolio, symbol),
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );

                CREATE TABLE IF NOT EXISTS prices (
                    id INTEGER PRIMARY KEY,
                    drill_id INTEGER NOT NULL,
                    portfolio TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    price REAL NOT NULL,
                    source TEXT NOT NULL,
                    source_timestamp TEXT NOT NULL,
                    period_start TEXT,
                    period_end TEXT,
                    captured_at TEXT NOT NULL,
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );

                CREATE TABLE IF NOT EXISTS signals (
                    id INTEGER PRIMARY KEY,
                    drill_id INTEGER NOT NULL,
                    portfolio TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    signal TEXT NOT NULL,
                    source TEXT NOT NULL,
                    ml_probability REAL,
                    ta_probability REAL,
                    fused_probability REAL NOT NULL DEFAULT 0.5,
                    confidence REAL NOT NULL DEFAULT 0,
                    threshold_used REAL NOT NULL DEFAULT 0.5,
                    policy_version TEXT NOT NULL DEFAULT '',
                    confirmation_json TEXT NOT NULL DEFAULT '{}',
                    reason TEXT NOT NULL,
                    decided_at TEXT NOT NULL,
                    UNIQUE (drill_id, portfolio, symbol, decided_at),
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );

                CREATE TABLE IF NOT EXISTS orders (
                    id INTEGER PRIMARY KEY,
                    drill_id INTEGER NOT NULL,
                    portfolio TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    reason TEXT NOT NULL,
                    status TEXT NOT NULL,
                    idempotency_key TEXT NOT NULL UNIQUE,
                    created_at TEXT NOT NULL,
                    filled_at TEXT,
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );

                CREATE TABLE IF NOT EXISTS fills (
                    id INTEGER PRIMARY KEY,
                    drill_id INTEGER NOT NULL,
                    order_id INTEGER NOT NULL UNIQUE,
                    portfolio TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    side TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    market_price REAL NOT NULL,
                    fill_price REAL NOT NULL,
                    fee REAL NOT NULL,
                    slippage REAL NOT NULL,
                    filled_at TEXT NOT NULL,
                    FOREIGN KEY (drill_id) REFERENCES drills(id),
                    FOREIGN KEY (order_id) REFERENCES orders(id)
                );

                CREATE TABLE IF NOT EXISTS positions (
                    id INTEGER PRIMARY KEY,
                    drill_id INTEGER NOT NULL,
                    portfolio TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    quantity REAL NOT NULL,
                    entry_price REAL NOT NULL,
                    stop_price REAL NOT NULL,
                    take_profit_price REAL NOT NULL,
                    entry_fee REAL NOT NULL,
                    entry_slippage REAL NOT NULL,
                    opened_at TEXT NOT NULL,
                    exit_price REAL,
                    exit_fee REAL NOT NULL DEFAULT 0,
                    exit_slippage REAL NOT NULL DEFAULT 0,
                    closed_at TEXT,
                    realized_pnl REAL,
                    close_reason TEXT NOT NULL DEFAULT '',
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );

                CREATE UNIQUE INDEX IF NOT EXISTS one_open_position
                ON positions(drill_id, portfolio, symbol)
                WHERE closed_at IS NULL;

                CREATE TABLE IF NOT EXISTS events (
                    id INTEGER PRIMARY KEY,
                    drill_id INTEGER NOT NULL,
                    category TEXT NOT NULL,
                    level TEXT NOT NULL,
                    message TEXT NOT NULL,
                    details_json TEXT NOT NULL,
                    occurred_at TEXT NOT NULL,
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );

                CREATE TABLE IF NOT EXISTS equity_points (
                    id INTEGER PRIMARY KEY,
                    drill_id INTEGER NOT NULL,
                    portfolio TEXT NOT NULL,
                    equity REAL NOT NULL,
                    cash REAL NOT NULL,
                    recorded_at TEXT NOT NULL,
                    UNIQUE (drill_id, portfolio, recorded_at),
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );

                CREATE TABLE IF NOT EXISTS entry_states (
                    drill_id INTEGER NOT NULL,
                    portfolio TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    state TEXT NOT NULL DEFAULT 'PENDING',
                    failures INTEGER NOT NULL DEFAULT 0,
                    reason TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (drill_id, portfolio, symbol),
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );

                CREATE TABLE IF NOT EXISTS symbol_health (
                    drill_id INTEGER NOT NULL,
                    portfolio TEXT NOT NULL,
                    symbol TEXT NOT NULL,
                    consecutive_failures INTEGER NOT NULL DEFAULT 0,
                    disabled INTEGER NOT NULL DEFAULT 0,
                    last_error TEXT NOT NULL DEFAULT '',
                    updated_at TEXT NOT NULL,
                    PRIMARY KEY (drill_id, portfolio, symbol),
                    FOREIGN KEY (drill_id) REFERENCES drills(id)
                );
                """
            )
            self._add_column(db, "prices", "period_start", "TEXT")
            self._add_column(db, "prices", "period_end", "TEXT")
            self._add_column(db, "signals", "fused_probability", "REAL NOT NULL DEFAULT 0.5")
            self._add_column(db, "signals", "confidence", "REAL NOT NULL DEFAULT 0")
            self._add_column(db, "signals", "threshold_used", "REAL NOT NULL DEFAULT 0.5")
            self._add_column(db, "signals", "policy_version", "TEXT NOT NULL DEFAULT ''")
            self._add_column(db, "signals", "confirmation_json", "TEXT NOT NULL DEFAULT '{}'")
            self._add_column(db, "drills", "profile_name", "TEXT NOT NULL DEFAULT 'one-day-drill'")
            self._add_column(db, "drills", "profile_version", "TEXT NOT NULL DEFAULT '1.0'")
            self._add_column(db, "drills", "execution_mode", "TEXT NOT NULL DEFAULT 'SIMULATED'")
            self._add_column(db, "drills", "scheduler_heartbeat_at", "TEXT")
            self._add_column(db, "drills", "last_cycle_at", "TEXT")
            self._add_column(db, "drills", "expired_reason", "TEXT NOT NULL DEFAULT ''")

    @staticmethod
    def _add_column(db: sqlite3.Connection, table: str, column: str, declaration: str) -> None:
        columns = {row["name"] for row in db.execute(f"PRAGMA table_info({table})")}
        if column not in columns:
            db.execute(f"ALTER TABLE {table} ADD COLUMN {column} {declaration}")

    @staticmethod
    def _now() -> str:
        return datetime.now(UTC).isoformat()

    @staticmethod
    def _rows(rows: list[sqlite3.Row]) -> list[dict[str, Any]]:
        return [dict(row) for row in rows]

    def create_drill(
        self,
        config: DrillConfig,
        *,
        profile_name: str = "one-day-drill",
        profile_version: str = "1.0",
        execution_mode: str = "SIMULATED",
    ) -> int:
        now = self._now()
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO drills(
                    session_date, status, config_json, created_at, updated_at,
                    profile_name, profile_version, execution_mode
                )
                VALUES (?, 'CREATED', ?, ?, ?, ?, ?, ?)
                ON CONFLICT(session_date) DO NOTHING
                """,
                (
                    config.session_date.isoformat(),
                    json.dumps(config.to_dict()),
                    now,
                    now,
                    profile_name,
                    profile_version,
                    execution_mode,
                ),
            )
            row = db.execute(
                "SELECT id FROM drills WHERE session_date = ?",
                (config.session_date.isoformat(),),
            ).fetchone()
            drill_id = int(row["id"])
            self._initialize_portfolios(db, drill_id, config)
            self._initialize_symbol_state(db, drill_id, config)
        return drill_id

    def _initialize_portfolios(
        self, db: sqlite3.Connection, drill_id: int, config: DrillConfig
    ) -> None:
        for kind, symbols in (
            ("STOCK", config.stock_symbols),
            ("CRYPTO", config.crypto_symbols),
        ):
            if not symbols:
                continue
            db.execute(
                """
                INSERT INTO portfolios(
                    drill_id, kind, initial_capital, cash, peak_equity
                ) VALUES (?, ?, ?, ?, ?)
                ON CONFLICT(drill_id, kind) DO NOTHING
                """,
                (
                    drill_id,
                    kind,
                    config.initial_capital,
                    config.initial_capital,
                    config.initial_capital,
                ),
            )

    def _initialize_symbol_state(
        self, db: sqlite3.Connection, drill_id: int, config: DrillConfig
    ) -> None:
        now = self._now()
        for portfolio, symbols in (
            ("STOCK", config.stock_symbols),
            ("CRYPTO", config.crypto_symbols),
        ):
            for symbol in symbols:
                db.execute(
                    """
                    INSERT OR IGNORE INTO entry_states(
                        drill_id, portfolio, symbol, state, updated_at
                    ) VALUES (?, ?, ?, 'PENDING', ?)
                    """,
                    (drill_id, portfolio, symbol, now),
                )
                db.execute(
                    """
                    INSERT OR IGNORE INTO symbol_health(
                        drill_id, portfolio, symbol, updated_at
                    ) VALUES (?, ?, ?, ?)
                    """,
                    (drill_id, portfolio, symbol, now),
                )

    def has_fills(self, drill_id: int) -> bool:
        with self.connection() as db:
            row = db.execute(
                "SELECT 1 FROM fills WHERE drill_id = ? LIMIT 1", (drill_id,)
            ).fetchone()
        return row is not None

    def reset_for_preparation(
        self,
        drill_id: int,
        config: DrillConfig,
        *,
        profile_name: str | None = None,
        profile_version: str | None = None,
        execution_mode: str | None = None,
    ) -> None:
        if self.has_fills(drill_id):
            raise ValueError("cannot force-prepare a drill that already has fills")
        with self.connection() as db:
            for table in (
                "model_preparations",
                "signals",
                "orders",
                "positions",
                "prices",
                "equity_points",
                "entry_states",
                "symbol_health",
                "portfolios",
            ):
                db.execute(f"DELETE FROM {table} WHERE drill_id = ?", (drill_id,))
            db.execute(
                """
                UPDATE drills
                SET status = 'CREATED', config_json = ?, halt_reason = '',
                    profile_name = COALESCE(?, profile_name),
                    profile_version = COALESCE(?, profile_version),
                    execution_mode = COALESCE(?, execution_mode),
                    scheduler_heartbeat_at = NULL, last_cycle_at = NULL,
                    expired_reason = '', updated_at = ?
                WHERE id = ?
                """,
                (
                    json.dumps(config.to_dict()),
                    profile_name,
                    profile_version,
                    execution_mode,
                    self._now(),
                    drill_id,
                ),
            )
            self._initialize_portfolios(db, drill_id, config)
            self._initialize_symbol_state(db, drill_id, config)

    def latest_drill_id(self) -> int | None:
        with self.connection() as db:
            row = db.execute("SELECT id FROM drills ORDER BY id DESC LIMIT 1").fetchone()
        return int(row["id"]) if row else None

    def next_actionable_drill_id(self, today: str) -> int | None:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT id FROM drills
                WHERE status IN ('CREATED', 'PREPARED', 'RUNNING')
                  AND session_date >= ?
                ORDER BY session_date ASC, id ASC
                LIMIT 1
                """,
                (today,),
            ).fetchone()
            if row is None:
                row = db.execute(
                    """
                    SELECT id FROM drills
                    WHERE status IN ('CREATED', 'PREPARED', 'RUNNING')
                    ORDER BY session_date DESC, id DESC
                    LIMIT 1
                    """
                ).fetchone()
        return int(row["id"]) if row else None

    def runs(self) -> list[dict[str, Any]]:
        with self.connection() as db:
            rows = db.execute("SELECT * FROM drills ORDER BY session_date DESC, id DESC").fetchall()
        results = self._rows(rows)
        for result in results:
            result["config"] = json.loads(result.pop("config_json"))
        return results

    def drill(self, drill_id: int) -> dict[str, Any]:
        with self.connection() as db:
            row = db.execute("SELECT * FROM drills WHERE id = ?", (drill_id,)).fetchone()
        if row is None:
            raise ValueError(f"Unknown drill {drill_id}")
        result = dict(row)
        result["config"] = json.loads(result.pop("config_json"))
        return result

    def set_status(self, drill_id: int, status: str, halt_reason: str = "") -> None:
        with self.connection() as db:
            db.execute(
                """
                UPDATE drills
                SET status = ?, halt_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, halt_reason, self._now(), drill_id),
            )

    def set_expired(self, drill_id: int, status: str, reason: str) -> None:
        with self.connection() as db:
            db.execute(
                """
                UPDATE drills
                SET status = ?, expired_reason = ?, updated_at = ?
                WHERE id = ?
                """,
                (status, reason, self._now(), drill_id),
            )

    def record_scheduler_heartbeat(self, drill_id: int, when: datetime) -> None:
        with self.connection() as db:
            db.execute(
                """
                UPDATE drills
                SET scheduler_heartbeat_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (when.isoformat(), self._now(), drill_id),
            )

    def record_cycle(self, drill_id: int, when: datetime) -> None:
        with self.connection() as db:
            db.execute(
                """
                UPDATE drills
                SET last_cycle_at = ?, scheduler_heartbeat_at = ?, updated_at = ?
                WHERE id = ?
                """,
                (when.isoformat(), when.isoformat(), self._now(), drill_id),
            )

    def record_preparation(
        self,
        drill_id: int,
        portfolio: str,
        symbol: str,
        *,
        approved: bool,
        source: str,
        metrics: dict[str, Any],
        reason: str,
        artifact_path: str | None = None,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO model_preparations(
                    drill_id, portfolio, symbol, approved, source, artifact_path,
                    metrics_json, reason, prepared_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                ON CONFLICT(drill_id, portfolio, symbol) DO UPDATE SET
                    approved = excluded.approved,
                    source = excluded.source,
                    artifact_path = excluded.artifact_path,
                    metrics_json = excluded.metrics_json,
                    reason = excluded.reason,
                    prepared_at = excluded.prepared_at
                """,
                (
                    drill_id,
                    portfolio,
                    symbol,
                    int(approved),
                    source,
                    artifact_path,
                    json.dumps(metrics, allow_nan=False),
                    reason,
                    self._now(),
                ),
            )

    def preparation(self, drill_id: int, portfolio: str, symbol: str) -> dict | None:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT * FROM model_preparations
                WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                """,
                (drill_id, portfolio, symbol),
            ).fetchone()
        if row is None:
            return None
        result = dict(row)
        result["metrics"] = json.loads(result.pop("metrics_json"))
        return result

    def record_price(self, drill_id: int, quote: PriceQuote) -> int:
        with self.connection() as db:
            cursor = db.execute(
                """
                INSERT INTO prices(
                    drill_id, portfolio, symbol, price, source,
                    source_timestamp, period_start, period_end, captured_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    drill_id,
                    quote.portfolio,
                    quote.symbol,
                    quote.price,
                    quote.source,
                    quote.source_timestamp.isoformat(),
                    quote.period_start.isoformat(),
                    quote.period_end.isoformat(),
                    quote.captured_at.isoformat(),
                ),
            )
            return int(cursor.lastrowid)

    def latest_price(self, drill_id: int, portfolio: str, symbol: str) -> dict | None:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT * FROM prices
                WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                ORDER BY captured_at DESC, id DESC LIMIT 1
                """,
                (drill_id, portfolio, symbol),
            ).fetchone()
        return dict(row) if row else None

    def record_signal(self, drill_id: int, decision: SignalDecision) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT OR IGNORE INTO signals(
                    drill_id, portfolio, symbol, signal, source, ml_probability,
                    ta_probability, fused_probability, confidence, threshold_used,
                    policy_version, confirmation_json, reason, decided_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    drill_id,
                    decision.portfolio,
                    decision.symbol,
                    decision.signal,
                    decision.source,
                    decision.ml_probability,
                    decision.ta_probability,
                    decision.fused_probability,
                    decision.confidence,
                    decision.threshold_used,
                    decision.policy_version,
                    json.dumps(decision.confirmation_details, sort_keys=True),
                    decision.reason,
                    decision.decided_at.isoformat(),
                ),
            )

    def entry_states(self, drill_id: int, state: str | None = None) -> list[dict]:
        sql = "SELECT * FROM entry_states WHERE drill_id = ?"
        params: list[Any] = [drill_id]
        if state:
            sql += " AND state = ?"
            params.append(state)
        sql += " ORDER BY portfolio, symbol"
        with self.connection() as db:
            return self._rows(db.execute(sql, params).fetchall())

    def set_entry_state(
        self,
        drill_id: int,
        portfolio: str,
        symbol: str,
        state: str,
        reason: str = "",
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                UPDATE entry_states
                SET state = ?, reason = ?, updated_at = ?
                WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                """,
                (state, reason, self._now(), drill_id, portfolio, symbol),
            )

    def record_entry_failure(
        self,
        drill_id: int,
        portfolio: str,
        symbol: str,
        reason: str,
        max_failures: int,
    ) -> int:
        with self.connection() as db:
            db.execute(
                """
                UPDATE entry_states
                SET failures = failures + 1, reason = ?, updated_at = ?
                WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                """,
                (reason, self._now(), drill_id, portfolio, symbol),
            )
            row = db.execute(
                """
                SELECT failures FROM entry_states
                WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                """,
                (drill_id, portfolio, symbol),
            ).fetchone()
            failures = int(row["failures"])
            if failures >= max_failures:
                db.execute(
                    """
                    UPDATE entry_states SET state = 'EXPIRED', updated_at = ?
                    WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                    """,
                    (self._now(), drill_id, portfolio, symbol),
                )
        return failures

    def symbol_health(self, drill_id: int) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT * FROM symbol_health
                WHERE drill_id = ? ORDER BY portfolio, symbol
                """,
                (drill_id,),
            ).fetchall()
        return self._rows(rows)

    def record_symbol_success(self, drill_id: int, portfolio: str, symbol: str) -> None:
        with self.connection() as db:
            db.execute(
                """
                UPDATE symbol_health
                SET consecutive_failures = 0, last_error = '', updated_at = ?
                WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                """,
                (self._now(), drill_id, portfolio, symbol),
            )

    def record_symbol_failure(
        self,
        drill_id: int,
        portfolio: str,
        symbol: str,
        error: str,
        max_failures: int,
    ) -> int:
        with self.connection() as db:
            db.execute(
                """
                UPDATE symbol_health
                SET consecutive_failures = consecutive_failures + 1,
                    last_error = ?, updated_at = ?
                WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                """,
                (error, self._now(), drill_id, portfolio, symbol),
            )
            row = db.execute(
                """
                SELECT consecutive_failures FROM symbol_health
                WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                """,
                (drill_id, portfolio, symbol),
            ).fetchone()
            failures = int(row["consecutive_failures"])
            if failures >= max_failures:
                db.execute(
                    """
                    UPDATE symbol_health SET disabled = 1, updated_at = ?
                    WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                    """,
                    (self._now(), drill_id, portfolio, symbol),
                )
        return failures

    def create_order(
        self,
        drill_id: int,
        portfolio: str,
        symbol: str,
        side: str,
        quantity: float,
        reason: str,
        idempotency_key: str,
        created_at: datetime,
    ) -> int:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO orders(
                    drill_id, portfolio, symbol, side, quantity, reason,
                    status, idempotency_key, created_at
                ) VALUES (?, ?, ?, ?, ?, ?, 'PENDING', ?, ?)
                ON CONFLICT(idempotency_key) DO NOTHING
                """,
                (
                    drill_id,
                    portfolio,
                    symbol,
                    side,
                    quantity,
                    reason,
                    idempotency_key,
                    created_at.isoformat(),
                ),
            )
            row = db.execute(
                "SELECT id FROM orders WHERE idempotency_key = ?",
                (idempotency_key,),
            ).fetchone()
            return int(row["id"])

    def pending_orders(self, drill_id: int) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                """
                SELECT * FROM orders
                WHERE drill_id = ? AND status = 'PENDING'
                ORDER BY id
                """,
                (drill_id,),
            ).fetchall()
        return self._rows(rows)

    def portfolio(self, drill_id: int, kind: str) -> dict:
        with self.connection() as db:
            row = db.execute(
                "SELECT * FROM portfolios WHERE drill_id = ? AND kind = ?",
                (drill_id, kind),
            ).fetchone()
        if row is None:
            raise ValueError(f"Missing {kind} portfolio for drill {drill_id}")
        return dict(row)

    def portfolios(self, drill_id: int) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM portfolios WHERE drill_id = ? ORDER BY kind",
                (drill_id,),
            ).fetchall()
        return self._rows(rows)

    def set_portfolio_halted(self, drill_id: int, kind: str, halted: bool) -> None:
        with self.connection() as db:
            db.execute(
                "UPDATE portfolios SET halted = ? WHERE drill_id = ? AND kind = ?",
                (int(halted), drill_id, kind),
            )

    def update_data_failures(self, drill_id: int, kind: str, failures: int) -> None:
        with self.connection() as db:
            db.execute(
                """
                UPDATE portfolios SET data_failures = ?
                WHERE drill_id = ? AND kind = ?
                """,
                (failures, drill_id, kind),
            )

    def open_positions(self, drill_id: int, portfolio: str | None = None) -> list[dict]:
        sql = "SELECT * FROM positions WHERE drill_id = ? AND closed_at IS NULL"
        params: list[Any] = [drill_id]
        if portfolio:
            sql += " AND portfolio = ?"
            params.append(portfolio)
        sql += " ORDER BY id"
        with self.connection() as db:
            rows = db.execute(sql, params).fetchall()
        return self._rows(rows)

    def positions(self, drill_id: int) -> list[dict]:
        with self.connection() as db:
            rows = db.execute(
                "SELECT * FROM positions WHERE drill_id = ? ORDER BY id",
                (drill_id,),
            ).fetchall()
        return self._rows(rows)

    def symbol_was_closed(self, drill_id: int, portfolio: str, symbol: str) -> bool:
        with self.connection() as db:
            row = db.execute(
                """
                SELECT 1 FROM positions
                WHERE drill_id = ? AND portfolio = ? AND symbol = ?
                  AND closed_at IS NOT NULL
                LIMIT 1
                """,
                (drill_id, portfolio, symbol),
            ).fetchone()
        return row is not None

    def apply_buy_fill(
        self,
        order: dict,
        *,
        market_price: float,
        fill_price: float,
        fee: float,
        slippage: float,
        stop_price: float,
        take_profit_price: float,
        filled_at: datetime,
    ) -> None:
        notional = fill_price * order["quantity"]
        total = notional + fee
        with self.connection() as db:
            portfolio = db.execute(
                """
                SELECT cash FROM portfolios
                WHERE drill_id = ? AND kind = ?
                """,
                (order["drill_id"], order["portfolio"]),
            ).fetchone()
            if portfolio is None or float(portfolio["cash"]) + 1e-9 < total:
                raise ValueError("insufficient simulated cash")
            db.execute(
                """
                UPDATE portfolios
                SET cash = cash - ?, fees = fees + ?, slippage = slippage + ?
                WHERE drill_id = ? AND kind = ?
                """,
                (total, fee, slippage, order["drill_id"], order["portfolio"]),
            )
            db.execute(
                """
                INSERT INTO positions(
                    drill_id, portfolio, symbol, quantity, entry_price,
                    stop_price, take_profit_price, entry_fee, entry_slippage,
                    opened_at
                ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
                """,
                (
                    order["drill_id"],
                    order["portfolio"],
                    order["symbol"],
                    order["quantity"],
                    fill_price,
                    stop_price,
                    take_profit_price,
                    fee,
                    slippage,
                    filled_at.isoformat(),
                ),
            )
            self._insert_fill(db, order, market_price, fill_price, fee, slippage, filled_at)

    def apply_sell_fill(
        self,
        order: dict,
        position: dict,
        *,
        market_price: float,
        fill_price: float,
        fee: float,
        slippage: float,
        filled_at: datetime,
    ) -> None:
        proceeds = fill_price * order["quantity"] - fee
        pnl = (
            (fill_price - position["entry_price"]) * order["quantity"] - position["entry_fee"] - fee
        )
        with self.connection() as db:
            db.execute(
                """
                UPDATE portfolios
                SET cash = cash + ?, realized_pnl = realized_pnl + ?,
                    fees = fees + ?, slippage = slippage + ?
                WHERE drill_id = ? AND kind = ?
                """,
                (
                    proceeds,
                    pnl,
                    fee,
                    slippage,
                    order["drill_id"],
                    order["portfolio"],
                ),
            )
            db.execute(
                """
                UPDATE positions
                SET exit_price = ?, exit_fee = ?, exit_slippage = ?,
                    closed_at = ?, realized_pnl = ?, close_reason = ?
                WHERE id = ?
                """,
                (
                    fill_price,
                    fee,
                    slippage,
                    filled_at.isoformat(),
                    pnl,
                    order["reason"],
                    position["id"],
                ),
            )
            self._insert_fill(db, order, market_price, fill_price, fee, slippage, filled_at)

    @staticmethod
    def _insert_fill(
        db: sqlite3.Connection,
        order: dict,
        market_price: float,
        fill_price: float,
        fee: float,
        slippage: float,
        filled_at: datetime,
    ) -> None:
        db.execute(
            """
            INSERT INTO fills(
                drill_id, order_id, portfolio, symbol, side, quantity,
                market_price, fill_price, fee, slippage, filled_at
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            """,
            (
                order["drill_id"],
                order["id"],
                order["portfolio"],
                order["symbol"],
                order["side"],
                order["quantity"],
                market_price,
                fill_price,
                fee,
                slippage,
                filled_at.isoformat(),
            ),
        )
        db.execute(
            "UPDATE orders SET status = 'FILLED', filled_at = ? WHERE id = ?",
            (filled_at.isoformat(), order["id"]),
        )

    def record_event(
        self,
        drill_id: int,
        category: str,
        message: str,
        *,
        level: str = "INFO",
        details: dict[str, Any] | None = None,
        occurred_at: datetime | None = None,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT INTO events(
                    drill_id, category, level, message, details_json, occurred_at
                ) VALUES (?, ?, ?, ?, ?, ?)
                """,
                (
                    drill_id,
                    category,
                    level,
                    message,
                    json.dumps(details or {}, default=str),
                    (occurred_at or datetime.now(UTC)).isoformat(),
                ),
            )

    def record_equity(
        self,
        drill_id: int,
        portfolio: str,
        equity: float,
        cash: float,
        recorded_at: datetime,
    ) -> None:
        with self.connection() as db:
            db.execute(
                """
                INSERT OR REPLACE INTO equity_points(
                    drill_id, portfolio, equity, cash, recorded_at
                ) VALUES (?, ?, ?, ?, ?)
                """,
                (drill_id, portfolio, equity, cash, recorded_at.isoformat()),
            )
            db.execute(
                """
                UPDATE portfolios
                SET peak_equity = MAX(peak_equity, ?)
                WHERE drill_id = ? AND kind = ?
                """,
                (equity, drill_id, portfolio),
            )

    def table(self, name: str, drill_id: int) -> list[dict]:
        allowed = {
            "signals",
            "orders",
            "fills",
            "positions",
            "events",
            "equity_points",
            "prices",
            "model_preparations",
            "entry_states",
            "symbol_health",
        }
        if name not in allowed:
            raise ValueError(f"Unsupported table {name}")
        with self.connection() as db:
            if name in {"model_preparations", "entry_states", "symbol_health"}:
                sql = """
                    SELECT * FROM model_preparations
                    WHERE drill_id = ? ORDER BY portfolio, symbol
                """
                sql = sql.replace("model_preparations", name)
            else:
                sql = f"SELECT * FROM {name} WHERE drill_id = ? ORDER BY id"
            rows = db.execute(sql, (drill_id,)).fetchall()
        results = self._rows(rows)
        for item in results:
            if "details_json" in item:
                item["details"] = json.loads(item.pop("details_json"))
            if "metrics_json" in item:
                item["metrics"] = json.loads(item.pop("metrics_json"))
            if "confirmation_json" in item:
                item["confirmation_details"] = json.loads(item.pop("confirmation_json"))
        return results
