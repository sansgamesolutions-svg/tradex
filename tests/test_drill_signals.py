from __future__ import annotations

from datetime import date

import pandas as pd

from tradex.drill.signals import completed_before


def test_completed_before_removes_session_and_future_bars():
    index = pd.date_range("2026-06-10", periods=4, freq="D", tz="UTC")
    frame = pd.DataFrame({"close": range(4)}, index=index)

    completed = completed_before(frame, date(2026, 6, 12))

    assert list(completed.index.date) == [date(2026, 6, 10), date(2026, 6, 11)]
