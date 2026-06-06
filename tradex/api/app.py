from __future__ import annotations

import logging
import logging.config
from contextlib import asynccontextmanager
from datetime import datetime, timezone

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from fastapi import FastAPI, HTTPException

from tradex.api.schemas import (
    BacktestRequest,
    BacktestResponse,
    PredictRequest,
    PredictResponse,
    TrainRequest,
    TrainResponse,
)
from tradex.config.settings import settings

logging.config.dictConfig({
    "version": 1,
    "disable_existing_loggers": False,
    "formatters": {
        "json": {
            "format": '{"time":"%(asctime)s","level":"%(levelname)s","name":"%(name)s","msg":%(message)s}',
        }
    },
    "handlers": {"console": {"class": "logging.StreamHandler", "formatter": "json"}},
    "root": {"level": "INFO", "handlers": ["console"]},
})
logger = logging.getLogger(__name__)

_scheduler = AsyncIOScheduler()


@asynccontextmanager
async def lifespan(app: FastAPI):
    if settings.schedule_assets:
        _scheduler.add_job(
            _scheduled_run,
            "cron",
            hour=settings.schedule_hour,
            minute=0,
            day_of_week="mon-fri",
            misfire_grace_time=300,
        )
        _scheduler.start()
        logger.info('"Scheduler started for %s"', settings.schedule_assets)
    yield
    if _scheduler.running:
        _scheduler.shutdown(wait=False)


app = FastAPI(title="TradeX API", version="0.1.0", lifespan=lifespan)


@app.get("/health")
def health() -> dict:
    return {"status": "ok", "version": "0.1.0"}


@app.post("/predict", response_model=PredictResponse)
def predict(req: PredictRequest) -> PredictResponse:
    try:
        from tradex.data.fetcher import fetch
        from tradex.data.preprocessor import build_features
        from tradex.indicators.technical import add_indicators
        from tradex.signals.combiner import SignalCombiner

        raw_df = fetch(req.asset, req.timeframe)
        raw_df = add_indicators(raw_df)
        features = build_features(raw_df)
        signal = SignalCombiner(req.model, req.asset, req.timeframe).predict(features, raw_df)

        return PredictResponse(
            asset=req.asset,
            timeframe=req.timeframe,
            signal=signal,
            timestamp=datetime.now(timezone.utc),
        )
    except ValueError as exc:
        raise HTTPException(status_code=404, detail=str(exc))
    except Exception as exc:
        logger.exception('"predict failed for %s"', req.asset)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/train", response_model=TrainResponse)
def train(req: TrainRequest) -> TrainResponse:
    try:
        from tradex.data.fetcher import fetch
        from tradex.data.preprocessor import build_features, make_target, train_test_split
        from tradex.indicators.technical import add_indicators
        from tradex.models import get_model

        raw_df = fetch(req.asset, req.timeframe, start=req.start, end=req.end)
        raw_df = add_indicators(raw_df)
        X = build_features(raw_df)
        y = make_target(raw_df)
        X_train, X_test, y_train, y_test = train_test_split(X, y)

        m = get_model(req.model)
        m.fit(X_train, y_train)
        metrics = m.evaluate(X_test, y_test)
        m.save(req.asset, req.timeframe)

        return TrainResponse(
            asset=req.asset, timeframe=req.timeframe, model=req.model, metrics=metrics
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception('"train failed for %s"', req.asset)
        raise HTTPException(status_code=500, detail=str(exc))


@app.post("/backtest", response_model=BacktestResponse)
def backtest(req: BacktestRequest) -> BacktestResponse:
    try:
        from tradex.backtester.engine import Backtester
        from tradex.data.fetcher import fetch
        from tradex.data.preprocessor import build_features
        from tradex.indicators.technical import add_indicators

        raw_df = fetch(req.asset, req.timeframe, start=req.start, end=req.end)
        raw_df = add_indicators(raw_df)
        features = build_features(raw_df)
        results = Backtester(req.model).run(features, raw_df)

        return BacktestResponse(
            asset=req.asset,
            timeframe=req.timeframe,
            total_return=results.total_return,
            sharpe_ratio=results.sharpe_ratio,
            max_drawdown=results.max_drawdown,
            win_rate=results.win_rate,
            n_trades=results.n_trades,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))
    except Exception as exc:
        logger.exception('"backtest failed for %s"', req.asset)
        raise HTTPException(status_code=500, detail=str(exc))


async def _scheduled_run() -> None:
    logger.info('"Running scheduled predictions"')
    for asset in settings.schedule_assets:
        try:
            result = predict(PredictRequest(asset=asset, timeframe=settings.default_timeframe))
            logger.info('"Scheduled signal %s: %s"', asset, result.signal)
        except Exception:
            logger.exception('"Scheduled prediction failed for %s"', asset)
