from __future__ import annotations

import math
from dataclasses import dataclass
from typing import Literal

Signal = Literal["BUY", "SELL", "HOLD"]
DecisionSource = Literal["ML_TA", "TA_ONLY"]


@dataclass(frozen=True)
class Decision:
    signal: Signal
    fused_probability: float
    confidence: float
    threshold_used: float
    ml_probability: float | None
    ta_probability: float
    source: DecisionSource
    policy_version: str
    confirmation_details: dict[str, bool]
    reason: str


class DecisionEngine:
    """Validate and fuse ML/TA inputs into an auditable directional decision."""

    def __init__(
        self,
        model_weight: float | None = None,
        ta_weight: float | None = None,
        signal_threshold: float | None = None,
        ta_only_threshold: float | None = None,
        policy_version: str | None = None,
    ) -> None:
        if signal_threshold is not None:
            self._validate_threshold(signal_threshold, "signal_threshold")
        if ta_only_threshold is not None:
            self._validate_threshold(ta_only_threshold, "ta_only_threshold")
        if model_weight is not None:
            self._validate_weight(model_weight, "model_weight")
        if ta_weight is not None:
            self._validate_weight(ta_weight, "ta_weight")
        if model_weight is not None and ta_weight is not None and model_weight + ta_weight <= 0:
            raise ValueError("model_weight and ta_weight cannot both be zero")
        self._model_weight = model_weight
        self._ta_weight = ta_weight
        self._signal_threshold = signal_threshold
        self._ta_only_threshold = ta_only_threshold
        self._policy_version = policy_version

    def decide(
        self,
        *,
        ml_probability: float | None,
        ta_probability: float,
        bullish_confirmed: bool = True,
        bearish_confirmed: bool = True,
        confirmation_details: dict[str, bool] | None = None,
    ) -> Decision:
        from tradex.config.settings import settings

        model_weight = (
            self._model_weight if self._model_weight is not None else settings.model_weight
        )
        ta_weight = self._ta_weight if self._ta_weight is not None else settings.ta_weight
        ml_ta_threshold = (
            self._signal_threshold
            if self._signal_threshold is not None
            else settings.signal_threshold
        )
        ta_only_threshold = (
            self._ta_only_threshold
            if self._ta_only_threshold is not None
            else settings.ta_only_signal_threshold
        )
        policy_version = self._policy_version or settings.decision_policy_version

        self._validate_probability(ta_probability, "ta_probability")
        if ml_probability is not None:
            self._validate_probability(ml_probability, "ml_probability")
        self._validate_weight(model_weight, "model_weight")
        self._validate_weight(ta_weight, "ta_weight")
        self._validate_threshold(ml_ta_threshold, "signal_threshold")
        self._validate_threshold(ta_only_threshold, "ta_only_signal_threshold")

        if ml_probability is not None:
            weight_sum = model_weight + ta_weight
            if weight_sum <= 0:
                raise ValueError("model_weight and ta_weight cannot both be zero")
            fused = (
                model_weight / weight_sum * ml_probability + ta_weight / weight_sum * ta_probability
            )
            source: DecisionSource = "ML_TA"
            threshold = ml_ta_threshold
            buy_allowed = True
            sell_allowed = True
        else:
            fused = ta_probability
            source = "TA_ONLY"
            threshold = ta_only_threshold
            buy_allowed = bullish_confirmed
            sell_allowed = bearish_confirmed

        if fused >= threshold and buy_allowed:
            signal: Signal = "BUY"
        elif fused <= 1.0 - threshold and sell_allowed:
            signal = "SELL"
        else:
            signal = "HOLD"

        confidence = abs(fused - 0.5) * 2.0
        details = dict(confirmation_details or {})
        details["bullish_confirmed"] = bullish_confirmed
        details["bearish_confirmed"] = bearish_confirmed
        ml_part = f", ml={ml_probability:.4f}" if ml_probability is not None else ""
        reason = (
            f"fused={fused:.4f}, confidence={confidence:.4f}, "
            f"threshold={threshold:.4f} (ta={ta_probability:.4f}{ml_part})"
        )
        if source == "TA_ONLY":
            reason += (
                f", bullish_confirmed={bullish_confirmed}, bearish_confirmed={bearish_confirmed}"
            )

        return Decision(
            signal=signal,
            fused_probability=fused,
            confidence=confidence,
            threshold_used=threshold,
            ml_probability=ml_probability,
            ta_probability=ta_probability,
            source=source,
            policy_version=policy_version,
            confirmation_details=details,
            reason=reason,
        )

    @staticmethod
    def _validate_probability(value: float, name: str) -> None:
        if not math.isfinite(value) or not 0.0 <= value <= 1.0:
            raise ValueError(f"{name} must be finite and within [0, 1]")

    @staticmethod
    def _validate_weight(value: float, name: str) -> None:
        if not math.isfinite(value) or value < 0:
            raise ValueError(f"{name} must be a non-negative finite number")

    @staticmethod
    def _validate_threshold(value: float, name: str) -> None:
        if not math.isfinite(value) or not 0.5 < value <= 1.0:
            raise ValueError(f"{name} must be finite and within (0.5, 1]")
