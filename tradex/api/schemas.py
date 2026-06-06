from __future__ import annotations

from datetime import datetime
from typing import Literal

from pydantic import BaseModel

ModelChoice = Literal["xgboost", "random_forest", "lstm"]
Signal = Literal["BUY", "SELL", "HOLD"]


class PredictRequest(BaseModel):
    asset: str
    timeframe: str = "1d"
    model: ModelChoice = "xgboost"


class PredictResponse(BaseModel):
    asset: str
    timeframe: str
    signal: Signal
    timestamp: datetime


class TrainRequest(BaseModel):
    asset: str
    timeframe: str = "1d"
    model: ModelChoice = "xgboost"
    start: str | None = None
    end: str | None = None


class TrainResponse(BaseModel):
    asset: str
    timeframe: str
    model: str
    metrics: dict[str, float]


class BacktestRequest(BaseModel):
    asset: str
    timeframe: str = "1d"
    start: str
    end: str | None = None
    model: ModelChoice = "xgboost"


class BacktestResponse(BaseModel):
    asset: str
    timeframe: str
    total_return: float
    sharpe_ratio: float
    max_drawdown: float
    win_rate: float
    n_trades: int
