"""Tests for naive_first_engine.dm_test.

Unit tests exercise dm_test's contract directly with hand-built error
arrays. The regression test at the bottom reconstructs a multi-split
scenario from tests/fixtures.py and checks it reproduces one published
Diebold-Mariano B/W pair from da-tese-ao-produto.md section 1.3 (see
build_ols_dm_splits_1h's docstring/module comment in fixtures.py for why
OLS 1h 0/4 was chosen and RF/ARIMA were not attempted).
"""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from naive_first_engine.dm_test import DMResult, dm_test

from .fixtures import build_ols_dm_splits_1h


def test_dm_test_returns_typed_result():
    rng = np.random.default_rng(1)
    errors_model = pd.Series(rng.normal(0, 1, size=200))
    errors_naive0 = pd.Series(rng.normal(0, 1, size=200))
    result = dm_test(errors_model, errors_naive0)
    assert isinstance(result, DMResult)
    assert isinstance(result.statistic, float)
    assert isinstance(result.p_value, float)
    assert result.verdict in ("better", "worse", "no significant difference")


def test_dm_test_verdict_better_when_model_errors_much_smaller():
    rng = np.random.default_rng(2)
    errors_naive0 = pd.Series(rng.normal(0, 1.0, size=1000))
    errors_model = pd.Series(rng.normal(0, 0.2, size=1000))
    result = dm_test(errors_model, errors_naive0)
    assert result.verdict == "better"
    assert result.statistic < 0
    assert result.p_value < 0.05


def test_dm_test_verdict_worse_when_model_errors_much_larger():
    rng = np.random.default_rng(3)
    errors_naive0 = pd.Series(rng.normal(0, 0.2, size=1000))
    errors_model = pd.Series(rng.normal(0, 1.0, size=1000))
    result = dm_test(errors_model, errors_naive0)
    assert result.verdict == "worse"
    assert result.statistic > 0
    assert result.p_value < 0.05


def test_dm_test_verdict_no_significant_difference_for_similar_errors():
    rng = np.random.default_rng(4)
    errors_naive0 = pd.Series(rng.normal(0, 1.0, size=500))
    errors_model = pd.Series(rng.normal(0, 1.0, size=500))
    result = dm_test(errors_model, errors_naive0)
    assert result.verdict == "no significant difference"
    assert result.p_value >= 0.05


def test_dm_test_accepts_numpy_arrays_not_just_series():
    rng = np.random.default_rng(5)
    errors_model = rng.normal(0, 1, size=100)
    errors_naive0 = rng.normal(0, 1, size=100)
    result = dm_test(errors_model, errors_naive0)
    assert isinstance(result, DMResult)


def test_dm_test_rejects_mismatched_shapes():
    errors_model = pd.Series(np.zeros(10))
    errors_naive0 = pd.Series(np.zeros(11))
    with pytest.raises(ValueError):
        dm_test(errors_model, errors_naive0)


def test_dm_test_signature_only_accepts_precomputed_errors():
    """Leakage-prevention check: dm_test must take exactly the two
    positional error-array parameters plus ``horizon`` — nothing resembling
    raw price/return data, and no bypass flag for the Harvey correction."""
    import inspect

    params = list(inspect.signature(dm_test).parameters)
    assert params == ["errors_model", "errors_naive0", "horizon"]


def test_dm_test_horizon_one_matches_uncorrected_reference():
    """horizon=1 must reduce (exactly, per the docstring's derivation) to the
    original uncorrected DM statistic: mean(d) / sqrt(d.var(ddof=1) / n)."""
    rng = np.random.default_rng(6)
    errors_model = rng.normal(0, 1, size=300)
    errors_naive0 = rng.normal(0, 1, size=300)

    result = dm_test(errors_model, errors_naive0, horizon=1)

    d = errors_model**2 - errors_naive0**2
    n = d.shape[0]
    uncorrected_statistic = d.mean() / np.sqrt(d.var(ddof=1) / n)

    assert result.statistic == pytest.approx(uncorrected_statistic, rel=1e-9)


def test_dm_test_overlapping_horizon_correction_changes_statistic_under_positive_autocorrelation():
    """With deliberate positive autocorrelation in d_t (built via an AR(1)-like
    construction) and horizon > 1, the Harvey-corrected statistic must differ
    from the naive (ddof=1, no-autocovariance) statistic — proof the
    correction terms are actually doing something on overlapping horizons."""
    rng = np.random.default_rng(7)
    n = 500
    noise = rng.normal(0, 1.0, size=n)
    ar_signal = np.zeros(n)
    for t in range(1, n):
        ar_signal[t] = 0.8 * ar_signal[t - 1] + noise[t]

    errors_naive0 = pd.Series(rng.normal(0, 1.0, size=n) + 3.0)
    errors_model = pd.Series(ar_signal)

    horizon = 5
    result = dm_test(errors_model, errors_naive0, horizon=horizon)

    d = np.asarray(errors_model, dtype=float) ** 2 - np.asarray(errors_naive0, dtype=float) ** 2
    naive_statistic = d.mean() / np.sqrt(d.var(ddof=1) / d.shape[0])

    assert result.statistic != pytest.approx(naive_statistic, rel=1e-6)


def test_dm_regression_reproduces_published_ols_1h_bw_pair():
    """Reconstructs 4 synthetic per-split (Naive0, OLS) error pairs (see
    build_ols_dm_splits_1h in fixtures.py for the construction and why this
    pair, not RF/ARIMA, was chosen) and checks the aggregated verdict counts
    match the published OLS 1h DM B/W = 0/4 (da-tese-ao-produto.md sec 1.3).
    """
    splits = build_ols_dm_splits_1h()
    results = [dm_test(s.errors_model, s.errors_naive0) for s in splits]

    better = sum(1 for r in results if r.verdict == "better")
    worse = sum(1 for r in results if r.verdict == "worse")
    no_diff = sum(1 for r in results if r.verdict == "no significant difference")

    assert (better, worse) == (0, 4)
    assert no_diff == 0
    assert better + worse + no_diff == len(splits)
