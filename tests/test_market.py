import pandas as pd

from fetch_market import _clean_history


def test_clean_history_sorts_and_drops_invalid_close():
    frame = pd.DataFrame(
        {"date": ["2026-08-07", "2026-08-05", "2026-08-06"], "close": [11, 10, None]}
    )
    result = _clean_history(frame)
    assert result.index[-1].date().isoformat() == "2026-08-07"
    assert list(result["close"]) == [10.0, 11.0]

