"""Live API endpoint test runner.

Starts the uvicorn server as a subprocess, runs all endpoint tests,
prints results, then shuts the server down.

Usage:
    uv run python scripts/test_endpoints.py
"""
from __future__ import annotations

import json
import subprocess
import sys
import time

import requests

BASE = "http://127.0.0.1:8001"
PASS = "\033[32mPASS\033[0m"
FAIL = "\033[31mFAIL\033[0m"


def start_server() -> subprocess.Popen:
    proc = subprocess.Popen(
        [
            "uv", "run", "uvicorn", "tradex.api.app:app",
            "--host", "127.0.0.1", "--port", "8001",
            "--log-level", "warning",
        ],
        stdout=subprocess.DEVNULL,
        stderr=subprocess.PIPE,
    )
    for _ in range(30):
        try:
            if requests.get(f"{BASE}/health", timeout=2).status_code == 200:
                print(f"  Server ready (pid={proc.pid})\n")
                return proc
        except Exception:
            pass
        time.sleep(1)
    out, err = proc.communicate(timeout=5)
    print("Server stderr:", err.decode())
    raise RuntimeError("Server failed to start within 30 s")


def check(
    label: str,
    method: str,
    path: str,
    payload: dict | None = None,
    expected: int = 200,
) -> bool:
    sep = "-" * 62
    print(sep)
    print(f"  {method} {path}")
    print(f"  {label}")
    if payload:
        print(f"  Body: {json.dumps(payload)}")
    print(sep)
    try:
        url = f"{BASE}{path}"
        r = (
            requests.get(url, timeout=180)
            if method == "GET"
            else requests.post(url, json=payload, timeout=180)
        )
        ok = r.status_code == expected
        badge = PASS if ok else FAIL
        print(f"  {badge}  status={r.status_code}  (expected {expected})")
        try:
            body = r.json()
            print(f"  {json.dumps(body, indent=2)}")
        except Exception:
            print(f"  {r.text[:300]}")
        print()
        return ok
    except Exception as exc:
        print(f"  {FAIL}  {exc}\n")
        return False


def main() -> int:
    print("\n" + "=" * 64)
    print("  TradeX - Live API endpoint tests")
    print("=" * 64 + "\n")
    print("  Starting server ...")

    server = start_server()
    results: list[bool] = []

    try:
        # 1 — Health
        results.append(check("Liveness probe", "GET", "/health"))

        # 2 — OpenAPI schema exists
        results.append(check("OpenAPI schema generated", "GET", "/openapi.json"))

        # 3 — Predict before training (TA-only fallback)
        results.append(check(
            "Predict AAPL  →  no trained model yet; falls back to TA-only",
            "POST", "/predict",
            {"asset": "AAPL", "timeframe": "1d", "model": "xgboost"},
        ))

        # 4 — Train
        results.append(check(
            "Train XGBoost on AAPL daily data from 2022-01-01  (may take ~30 s)",
            "POST", "/train",
            {"asset": "AAPL", "timeframe": "1d", "model": "xgboost", "start": "2022-01-01"},
        ))

        # 5 — Predict after training
        results.append(check(
            "Predict AAPL after training  →  hybrid ML + TA signal",
            "POST", "/predict",
            {"asset": "AAPL", "timeframe": "1d", "model": "xgboost"},
        ))

        # 6 — Backtest
        results.append(check(
            "Backtest AAPL for calendar year 2023",
            "POST", "/backtest",
            {"asset": "AAPL", "timeframe": "1d", "start": "2023-01-01", "end": "2023-12-31"},
        ))

        # 7 — Crypto symbol mapping
        results.append(check(
            "Predict BTC  →  verifies crypto symbol → BTC-USD mapping",
            "POST", "/predict",
            {"asset": "BTC", "timeframe": "1d"},
        ))

        # 8 — Error: unknown asset
        results.append(check(
            "Unknown asset  →  expect 404",
            "POST", "/predict",
            {"asset": "INVALID_ASSET_XYZ_999"},
            expected=404,
        ))

        # 9 — Validation error: missing required field
        results.append(check(
            "Backtest without required 'start' field  →  expect 422",
            "POST", "/backtest",
            {"asset": "AAPL"},
            expected=422,
        ))

        # 10 — Wrong model type handled by Pydantic
        results.append(check(
            "Invalid model name in predict  →  expect 422",
            "POST", "/predict",
            {"asset": "AAPL", "model": "not_a_real_model"},
            expected=422,
        ))

    finally:
        server.terminate()
        server.wait(timeout=5)

    passed = sum(results)
    total = len(results)
    print("=" * 64)
    badge = PASS if passed == total else FAIL
    print(f"  {badge}  {passed}/{total} tests passed")
    print("=" * 64 + "\n")
    return 0 if passed == total else 1


if __name__ == "__main__":
    sys.exit(main())
