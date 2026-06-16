# Automatic Trading System

TradeX now has a reusable automatic trading core under `tradex.auto`. The first
deployment profile is `one-day-drill`, which is production-shaped but uses
simulated execution only.

## Commands

```powershell
uv run python -m tradex auto profiles
uv run python -m tradex auto prepare --profile one-day-drill --date 2026-06-17 --force
uv run python -m tradex auto run --profile one-day-drill --date 2026-06-17
uv run python -m tradex auto status
uv run python -m tradex auto halt --yes
```

The existing `tradex drill ...` commands remain aliases for the `one-day-drill`
profile.

## Runtime

FastAPI starts a single automation worker by default. The worker is simulated
only and cannot construct IBKR or authenticated Kraken broker clients. Use:

- `GET /api/auto/health`
- `GET /api/auto/status`
- `GET /api/auto/runs`
- `GET /api/auto/profiles`
- `POST /api/auto/halt`

The dashboard at `http://127.0.0.1:8000/drill` reads the automatic trading
status endpoint and displays the active profile, execution mode, market phase,
heartbeat, and policy version.

## Safety

- V1 execution mode is `SIMULATED`.
- `BROKER_PAPER` and `BROKER_LIVE` fail closed with an auditable event.
- Manual `tradex trade --submit` behavior is unchanged.
- Past unstarted sessions are marked `COMPLETED_NO_RUN` and produce reports
  instead of replaying stale activity.
