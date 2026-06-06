import pytest
from tradex.models.ml.random_forest import RandomForestModel
from tradex.models.ml.xgboost_model import XGBoostModel
from tradex.models import get_model


def test_random_forest_predict_proba(feature_df, binary_target):
    m = RandomForestModel(n_estimators=10)
    m.fit(feature_df, binary_target)
    prob = m.predict_proba(feature_df)
    assert 0.0 <= prob <= 1.0


def test_xgboost_predict_proba(feature_df, binary_target):
    m = XGBoostModel(n_estimators=10)
    m.fit(feature_df, binary_target)
    prob = m.predict_proba(feature_df)
    assert 0.0 <= prob <= 1.0


def test_evaluate_returns_accuracy_and_auc(feature_df, binary_target):
    m = RandomForestModel(n_estimators=10)
    m.fit(feature_df, binary_target)
    metrics = m.evaluate(feature_df, binary_target)
    assert "accuracy" in metrics
    assert "roc_auc" in metrics
    assert 0.0 <= metrics["accuracy"] <= 1.0


def test_get_model_unknown_raises():
    with pytest.raises(ValueError, match="Unknown model"):
        get_model("nonexistent")


def test_predict_returns_binary(feature_df, binary_target):
    m = XGBoostModel(n_estimators=10)
    m.fit(feature_df, binary_target)
    result = m.predict(feature_df)
    assert result in (0, 1)
