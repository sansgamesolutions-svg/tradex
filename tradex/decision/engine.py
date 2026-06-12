from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True)
class Decision:
    signal: str
    fused_probability: float
    ml_probability: float | None
    ta_probability: float
    source: str
    reason: str


class DecisionEngine:
    """Fuses ML probability and TA probability into a directional decision.

    Weights and threshold default to live settings values; pass explicit floats
    to override (useful in tests or for per-asset tuning).
    """

    def __init__(
        self,
        model_weight: float | None = None,
        ta_weight: float | None = None,
        signal_threshold: float | None = None,
    ) -> None:
        self._model_weight = model_weight
        self._ta_weight = ta_weight
        self._signal_threshold = signal_threshold

    def decide(
        self,
        *,
        ml_probability: float | None,
        ta_probability: float,
    ) -> Decision:
        """Return a Decision for the given probabilities.

        When *ml_probability* is None the engine falls back to TA-only:
        fused = ta_probability, source = "TA_ONLY".
        When both are present: fused = model_weight*ml + ta_weight*ta,
        source = "ML_TA".
        """
        from tradex.config.settings import settings

        model_weight = (
            self._model_weight if self._model_weight is not None else settings.model_weight
        )
        ta_weight = self._ta_weight if self._ta_weight is not None else settings.ta_weight
        threshold = (
            self._signal_threshold
            if self._signal_threshold is not None
            else settings.signal_threshold
        )

        if ml_probability is not None:
            fused = model_weight * ml_probability + ta_weight * ta_probability
            source = "ML_TA"
        else:
            fused = ta_probability
            source = "TA_ONLY"

        if fused >= threshold:
            signal = "BUY"
        elif fused <= 1.0 - threshold:
            signal = "SELL"
        else:
            signal = "HOLD"

        ml_part = f", ml={ml_probability:.4f}" if ml_probability is not None else ""
        reason = f"fused={fused:.4f} (ta={ta_probability:.4f}{ml_part})"

        return Decision(
            signal=signal,
            fused_probability=fused,
            ml_probability=ml_probability,
            ta_probability=ta_probability,
            source=source,
            reason=reason,
        )
