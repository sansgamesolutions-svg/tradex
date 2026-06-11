#!/usr/bin/env python
"""Standalone batch prediction runner.

Designed to be invoked by any external scheduler:
  - Kubernetes CronJob:   command: ["python", "-m", "scripts.batch_predict"]
  - AWS EventBridge:      ECS task override
  - GCP Cloud Scheduler:  Cloud Run job
  - Local cron:           0 9 * * 1-5 cd /app && python -m scripts.batch_predict

Environment variables:
  TRADEX_BATCH_ASSETS    Comma-separated symbols, e.g. "AAPL,BTC,MSFT"
  TRADEX_BATCH_TIMEFRAME Candle timeframe (default: 1d)
  TRADEX_BATCH_MODEL     Model to use (default: xgboost)
"""

from __future__ import annotations

import json
import logging
import os
import sys
from datetime import UTC, datetime

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(message)s")
logger = logging.getLogger(__name__)


def main() -> int:
    raw = os.getenv("TRADEX_BATCH_ASSETS", "")
    assets = [a.strip() for a in raw.split(",") if a.strip()]
    if not assets:
        logger.error("No assets configured. Set TRADEX_BATCH_ASSETS=AAPL,BTC,...")
        return 1

    timeframe = os.getenv("TRADEX_BATCH_TIMEFRAME", "1d")
    model_name = os.getenv("TRADEX_BATCH_MODEL", "xgboost")

    from tradex.data.fetcher import fetch
    from tradex.data.preprocessor import build_features
    from tradex.indicators.technical import add_indicators
    from tradex.signals.combiner import SignalCombiner

    results = []
    failed = 0

    for asset in assets:
        try:
            raw_df = fetch(asset, timeframe)
            raw_df = add_indicators(raw_df)
            features = build_features(raw_df)
            signal = SignalCombiner(model_name, asset, timeframe).predict(features, raw_df)
            results.append({"asset": asset, "signal": signal, "status": "ok"})
            logger.info("%-10s  %s", asset, signal)
        except Exception as exc:
            results.append({"asset": asset, "signal": None, "status": "error", "error": str(exc)})
            logger.error("%-10s  FAILED — %s", asset, exc)
            failed += 1

    print(
        json.dumps(
            {
                "timestamp": datetime.now(UTC).isoformat(),
                "timeframe": timeframe,
                "model": model_name,
                "results": results,
            },
            indent=2,
        )
    )

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
