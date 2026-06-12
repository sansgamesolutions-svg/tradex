from __future__ import annotations

import pytest

from tradex.decision import Decision, DecisionEngine


@pytest.fixture
def engine():
    return DecisionEngine(model_weight=0.6, ta_weight=0.4, signal_threshold=0.55)


def test_buy_signal_ml_ta(engine):
    d = engine.decide(ml_probability=0.8, ta_probability=0.7)
    assert d.signal == "BUY"
    assert d.source == "ML_TA"
    assert d.fused_probability == pytest.approx(0.6 * 0.8 + 0.4 * 0.7)


def test_sell_signal_ml_ta(engine):
    d = engine.decide(ml_probability=0.1, ta_probability=0.2)
    assert d.signal == "SELL"
    assert d.source == "ML_TA"
    assert d.fused_probability == pytest.approx(0.6 * 0.1 + 0.4 * 0.2)


def test_hold_signal_ml_ta(engine):
    d = engine.decide(ml_probability=0.5, ta_probability=0.5)
    assert d.signal == "HOLD"
    assert d.fused_probability == pytest.approx(0.5)


def test_ta_only_buy(engine):
    d = engine.decide(ml_probability=None, ta_probability=0.8)
    assert d.signal == "BUY"
    assert d.source == "TA_ONLY"
    assert d.fused_probability == pytest.approx(0.8)
    assert d.ml_probability is None


def test_ta_only_sell(engine):
    d = engine.decide(ml_probability=None, ta_probability=0.1)
    assert d.signal == "SELL"
    assert d.source == "TA_ONLY"


def test_ta_only_hold(engine):
    d = engine.decide(ml_probability=None, ta_probability=0.5)
    assert d.signal == "HOLD"
    assert d.source == "TA_ONLY"
    assert d.fused_probability == pytest.approx(0.5)


def test_boundary_buy_at_threshold(engine):
    d = engine.decide(ml_probability=None, ta_probability=0.55)
    assert d.signal == "BUY"


def test_boundary_sell_below_threshold(engine):
    # 1.0 - 0.55 == 0.4499... in IEEE 754; use 0.44 to reliably fall in SELL zone
    d = engine.decide(ml_probability=None, ta_probability=0.44)
    assert d.signal == "SELL"


def test_reason_includes_all_components_ml_ta(engine):
    d = engine.decide(ml_probability=0.7, ta_probability=0.6)
    assert "fused=" in d.reason
    assert "ta=" in d.reason
    assert "ml=" in d.reason


def test_reason_excludes_ml_for_ta_only(engine):
    d = engine.decide(ml_probability=None, ta_probability=0.6)
    assert "fused=" in d.reason
    assert "ta=" in d.reason
    assert "ml=" not in d.reason


def test_decision_is_frozen(engine):
    d = engine.decide(ml_probability=0.7, ta_probability=0.6)
    with pytest.raises((AttributeError, TypeError)):
        d.signal = "HOLD"  # type: ignore[misc]


def test_decision_type(engine):
    d = engine.decide(ml_probability=0.7, ta_probability=0.6)
    assert isinstance(d, Decision)
