from __future__ import annotations

import math

import pytest

from tradex.decision import DecisionEngine


@pytest.fixture
def engine():
    return DecisionEngine(
        model_weight=0.6,
        ta_weight=0.4,
        signal_threshold=0.55,
        ta_only_threshold=0.65,
        policy_version="test-v2",
    )


def test_ml_ta_uses_normalized_weights_and_metadata():
    decision = DecisionEngine(
        model_weight=6,
        ta_weight=4,
        signal_threshold=0.55,
        ta_only_threshold=0.65,
        policy_version="v2",
    ).decide(ml_probability=0.8, ta_probability=0.7)

    assert decision.signal == "BUY"
    assert decision.fused_probability == pytest.approx(0.76)
    assert decision.confidence == pytest.approx(0.52)
    assert decision.threshold_used == 0.55
    assert decision.policy_version == "v2"


def test_ta_only_requires_strict_bullish_confirmation(engine):
    blocked = engine.decide(
        ml_probability=None,
        ta_probability=0.8,
        bullish_confirmed=False,
    )
    allowed = engine.decide(
        ml_probability=None,
        ta_probability=0.65,
        bullish_confirmed=True,
    )

    assert blocked.signal == "HOLD"
    assert allowed.signal == "BUY"
    assert allowed.threshold_used == 0.65


def test_ta_only_requires_symmetric_bearish_confirmation(engine):
    blocked = engine.decide(
        ml_probability=None,
        ta_probability=0.1,
        bearish_confirmed=False,
    )
    allowed = engine.decide(
        ml_probability=None,
        ta_probability=0.1,
        bearish_confirmed=True,
    )

    assert blocked.signal == "HOLD"
    assert allowed.signal == "SELL"


@pytest.mark.parametrize("value", [math.nan, math.inf, -0.01, 1.01])
def test_invalid_probabilities_are_rejected(engine, value):
    with pytest.raises(ValueError, match="within"):
        engine.decide(ml_probability=value, ta_probability=0.5)


@pytest.mark.parametrize(
    ("kwargs", "message"),
    [
        ({"model_weight": -1}, "non-negative"),
        ({"ta_weight": math.nan}, "non-negative"),
        ({"signal_threshold": 0.5}, "within"),
        ({"ta_only_threshold": 1.01}, "within"),
        ({"model_weight": 0, "ta_weight": 0}, "both be zero"),
    ],
)
def test_malformed_policy_is_rejected(kwargs, message):
    with pytest.raises(ValueError, match=message):
        DecisionEngine(**kwargs)
