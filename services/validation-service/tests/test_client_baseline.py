"""VS-017: `ClientPredictionBaseline` unit tests.

Covers: correct-values lookup for a fully-covered `test.index`, and the
required ValueError (never a silent NaN-fill, never a bare KeyError) when the
client series is missing a required test-index timestamp.
"""

from __future__ import annotations

import pandas as pd
import pytest

from app.client_baseline import CLIENT_PREDICTION_AUDIT_DISCLAIMER, ClientPredictionBaseline


def _series(values: dict) -> pd.Series:
    index = pd.DatetimeIndex(list(values.keys()))
    return pd.Series(list(values.values()), index=index, dtype="float64")


def test_predict_returns_correct_values_for_fully_covered_test_index() -> None:
    client_series = _series(
        {
            "2024-01-01T00:00:00": 1.0,
            "2024-01-01T01:00:00": 2.0,
            "2024-01-01T02:00:00": 3.0,
            "2024-01-01T03:00:00": 4.0,
        }
    )
    baseline = ClientPredictionBaseline(client_series)

    train = _series({"2024-01-01T00:00:00": 1.0, "2024-01-01T01:00:00": 2.0})
    test = _series({"2024-01-01T02:00:00": 0.0, "2024-01-01T03:00:00": 0.0})

    predicted = baseline.predict(train, test)

    assert list(predicted.index) == list(test.index)
    assert predicted.loc["2024-01-01T02:00:00"] == 3.0
    assert predicted.loc["2024-01-01T03:00:00"] == 4.0


def test_predict_raises_value_error_not_key_error_on_missing_timestamp() -> None:
    client_series = _series({"2024-01-01T00:00:00": 1.0, "2024-01-01T01:00:00": 2.0})
    baseline = ClientPredictionBaseline(client_series)

    train = _series({"2024-01-01T00:00:00": 1.0})
    # 02:00 is not present in client_series.
    test = _series({"2024-01-01T01:00:00": 0.0, "2024-01-01T02:00:00": 0.0})

    with pytest.raises(ValueError) as exc_info:
        baseline.predict(train, test)

    assert not isinstance(exc_info.value, KeyError)
    assert "2024-01-01 02:00:00" in str(exc_info.value)


def test_predict_never_silently_fills_missing_timestamps_with_nan() -> None:
    client_series = _series({"2024-01-01T00:00:00": 1.0})
    baseline = ClientPredictionBaseline(client_series)

    train = _series({"2024-01-01T00:00:00": 1.0})
    test = _series({"2024-01-01T00:00:00": 0.0, "2024-01-01T01:00:00": 0.0})

    # If this silently NaN-filled instead of raising, the test below would
    # catch a Series with a NaN in it rather than a ValueError.
    with pytest.raises(ValueError):
        baseline.predict(train, test)


def test_disclaimer_covers_both_required_clauses() -> None:
    # Comparison-audited clause.
    assert "comparison" in CLIENT_PREDICTION_AUDIT_DISCLAIMER
    assert "naive baselines" in CLIENT_PREDICTION_AUDIT_DISCLAIMER
    # Provenance-not-certified clause.
    assert "does not certify the provenance" in CLIENT_PREDICTION_AUDIT_DISCLAIMER
    assert "leakage" in CLIENT_PREDICTION_AUDIT_DISCLAIMER
