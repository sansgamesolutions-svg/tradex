from __future__ import annotations

from tradex.models.base import BaseModel
from tradex.models.dl.lstm import LSTMModel
from tradex.models.ml.random_forest import RandomForestModel
from tradex.models.ml.xgboost_model import XGBoostModel

_REGISTRY: dict[str, type[BaseModel]] = {
    "random_forest": RandomForestModel,
    "xgboost": XGBoostModel,
    "lstm": LSTMModel,
}


def get_model(name: str, **kwargs) -> BaseModel:
    cls = _REGISTRY.get(name)
    if cls is None:
        raise ValueError(f"Unknown model '{name}'. Choose from: {list(_REGISTRY)}")
    return cls(**kwargs)


__all__ = ["BaseModel", "RandomForestModel", "XGBoostModel", "LSTMModel", "get_model"]
