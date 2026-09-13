"""MR-001: unit tests on `detect_price_level_series` directly.

Fixed seeds throughout for determinism, mirroring this repo's existing
synthetic-fixture convention (`test_split_count_guardrail.py`,
`test_regression_api.py`).
"""

from __future__ import annotations

import numpy as np
import pandas as pd

from app.level_detection import detect_price_level_series


def test_price_level_like_series_is_flagged():
    rng = np.random.default_rng(42)
    n = 500
    increments = rng.normal(0.0, 5.0, size=n)
    levels = 20000.0 + np.cumsum(increments)
    index = pd.date_range("2024-01-01", periods=n, freq="h")
    series = pd.Series(levels, index=index)

    result = detect_price_level_series(series)

    assert result.is_price_level is True
    assert result.lag1_autocorr > 0.90
    assert abs(result.mean_over_std) > 1.0


def test_returns_like_series_is_not_flagged():
    rng = np.random.default_rng(42)
    n = 500
    returns = rng.normal(0.0, 0.01, size=n)
    index = pd.date_range("2024-01-01", periods=n, freq="h")
    series = pd.Series(returns, index=index)

    result = detect_price_level_series(series)

    assert result.is_price_level is False
