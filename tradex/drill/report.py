from __future__ import annotations

import html
import json
from datetime import UTC, datetime
from pathlib import Path

from tradex.drill.store import DrillStore
from tradex.drill.types import DrillReport


def build_report(store: DrillStore, drill_id: int) -> DrillReport:
    drill = store.drill(drill_id)
    positions = store.positions(drill_id)
    equity = store.table("equity_points", drill_id)
    signals = store.table("signals", drill_id)
    events = store.table("events", drill_id)
    portfolio_reports: list[dict] = []
    session_start = datetime.fromisoformat(f"{drill['session_date']}T09:30:00-04:00")
    session_end = datetime.fromisoformat(f"{drill['session_date']}T16:00:00-04:00")
    session_seconds = (session_end - session_start).total_seconds()

    for portfolio in store.portfolios(drill_id):
        kind = portfolio["kind"]
        points = [point for point in equity if point["portfolio"] == kind]
        final_equity = points[-1]["equity"] if points else portfolio["cash"]
        initial = portfolio["initial_capital"]
        closed = [
            position
            for position in positions
            if position["portfolio"] == kind and position["closed_at"]
        ]
        wins = sum(float(position["realized_pnl"]) > 0 for position in closed)
        gross_pnl = sum(
            (float(position["exit_price"]) - float(position["entry_price"]))
            * float(position["quantity"])
            for position in closed
        )
        exposure_dollars_seconds = 0.0
        for position in positions:
            if position["portfolio"] != kind:
                continue
            opened = max(datetime.fromisoformat(position["opened_at"]), session_start)
            closed_at = (
                datetime.fromisoformat(position["closed_at"])
                if position["closed_at"]
                else session_end
            )
            closed_at = min(closed_at, session_end)
            duration = max((closed_at - opened).total_seconds(), 0.0)
            exposure_dollars_seconds += (
                float(position["entry_price"]) * float(position["quantity"]) * duration
            )
        max_drawdown = 0.0
        peak = initial
        for point in points:
            peak = max(peak, float(point["equity"]))
            max_drawdown = min(max_drawdown, (float(point["equity"]) - peak) / peak)
        portfolio_reports.append(
            {
                "kind": kind,
                "initial_capital": initial,
                "final_equity": final_equity,
                "net_pnl": final_equity - initial,
                "net_return": (final_equity - initial) / initial,
                "gross_pnl_without_costs": gross_pnl,
                "gross_return_without_costs": gross_pnl / initial,
                "fees": portfolio["fees"],
                "slippage": portfolio["slippage"],
                "max_drawdown": max_drawdown,
                "average_capital_exposure": (
                    exposure_dollars_seconds / (initial * session_seconds)
                ),
                "closed_trades": len(closed),
                "win_rate": wins / len(closed) if closed else 0.0,
                "rejected_signals": sum(
                    event["category"] == "RISK"
                    and event["message"].startswith(f"{kind} ")
                    and "entry rejected" in event["message"]
                    for event in events
                ),
                "stale_data_events": sum(
                    event["category"] in {"DATA", "RISK"}
                    and event["message"].startswith(f"{kind} ")
                    and "stale" in event["message"].lower()
                    for event in events
                ),
                "halted": bool(portfolio["halted"]),
                "benchmark_5_percent": initial * 1.05,
                "benchmark_10_percent": initial * 1.10,
            }
        )

    total_initial = sum(item["initial_capital"] for item in portfolio_reports)
    total_final = sum(item["final_equity"] for item in portfolio_reports)
    recommendations = _recommendations(portfolio_reports, signals, events)
    return DrillReport(
        drill_id=drill_id,
        session_date=drill["session_date"],
        status=drill["status"],
        generated_at=datetime.now(UTC).isoformat(),
        portfolios=tuple(portfolio_reports),
        combined={
            "initial_capital": total_initial,
            "final_equity": total_final,
            "net_pnl": total_final - total_initial,
            "net_return": (total_final - total_initial) / total_initial,
            "benchmark_5_percent": total_initial * 1.05,
            "benchmark_10_percent": total_initial * 1.10,
        },
        signals=tuple(signals),
        positions=tuple(positions),
        events=tuple(events),
        equity_curve=tuple(equity),
        recommendations=tuple(recommendations),
    )


def _recommendations(
    portfolios: list[dict],
    signals: list[dict],
    events: list[dict],
) -> list[dict]:
    recommendations = [
        {
            "category": "operations",
            "message": ("Run at least 20 paper sessions before changing model or risk thresholds."),
        }
    ]
    if any(event["category"] == "DATA" and event["level"] != "INFO" for event in events):
        recommendations.append(
            {
                "category": "data-quality",
                "message": (
                    "Add a secondary quote provider and alert on repeated stale or missing data."
                ),
            }
        )
    if not any(signal["signal"] == "BUY" for signal in signals):
        recommendations.append(
            {
                "category": "signal",
                "message": (
                    "Review signal coverage across multiple sessions; "
                    "do not lower thresholds from one day."
                ),
            }
        )
    if any(item["fees"] + item["slippage"] > abs(item["net_pnl"]) for item in portfolios):
        recommendations.append(
            {
                "category": "execution",
                "message": (
                    "Costs dominated results; test passive limit fills and lower-turnover rules."
                ),
            }
        )
    if any(item["max_drawdown"] <= -0.01 for item in portfolios):
        recommendations.append(
            {
                "category": "risk",
                "message": (
                    "The portfolio loss halt triggered; "
                    "review position correlation and entry timing."
                ),
            }
        )
    return recommendations


def write_report(report: DrillReport, path: Path, output_format: str) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    payload = report.to_dict()
    if output_format == "json":
        path.write_text(json.dumps(payload, indent=2, sort_keys=True) + "\n", encoding="utf-8")
        return path

    cards = "".join(
        (
            f"<section><h2>{html.escape(item['kind'])}</h2>"
            f"<p>Final equity: ${item['final_equity']:,.2f}</p>"
            f"<p>Net return: {item['net_return']:.2%}</p>"
            f"<p>Trades: {item['closed_trades']} | Win rate: {item['win_rate']:.2%}</p>"
            f"<p>Fees: ${item['fees']:,.2f} | Slippage: ${item['slippage']:,.2f}</p>"
            "</section>"
        )
        for item in payload["portfolios"]
    )
    recommendations = "".join(
        f"<li><strong>{html.escape(item['category'])}:</strong> {html.escape(item['message'])}</li>"
        for item in payload["recommendations"]
    )
    document = f"""<!doctype html>
<html lang="en">
<head><meta charset="utf-8"><title>TradeX Drill Report</title>
<style>
body{{font-family:system-ui;max-width:960px;margin:2rem auto;padding:0 1rem;
background:#0b1220;color:#e5e7eb}}
section{{background:#111827;padding:1rem;margin:1rem 0;border-radius:.75rem}}
h1,h2{{color:#60a5fa}} code{{color:#fbbf24}}
</style></head>
<body><h1>TradeX Drill Report</h1>
<p>Session: {html.escape(report.session_date)} | Status: {html.escape(report.status)}</p>
{cards}
<section><h2>Combined</h2><p>Final equity: ${payload["combined"]["final_equity"]:,.2f}</p>
<p>Net return: {payload["combined"]["net_return"]:.2%}</p></section>
<section><h2>Recommendations</h2><ul>{recommendations}</ul></section>
</body></html>"""
    path.write_text(document, encoding="utf-8")
    return path
