from __future__ import annotations

from tradex.indicators.technical import assess_technical


def check_timeframe_alignment(
    asset: str,
    primary_signal: str,
    confirmation_timeframes: list[str],
    model_name: str = "xgboost",
) -> bool:
    """Return True if every confirmation timeframe's TA agrees with primary_signal direction."""
    if not confirmation_timeframes or primary_signal == "HOLD":
        return True

    from tradex.data.fetcher import fetch
    from tradex.indicators.technical import add_indicators

    for tf in confirmation_timeframes:
        try:
            df = fetch(asset, tf)
            df = add_indicators(df)
        except Exception:
            return False

        assessment = assess_technical(df)
        if primary_signal == "BUY" and not assessment.bullish_confirmed:
            return False
        if primary_signal == "SELL" and not assessment.bearish_confirmed:
            return False

    return True
