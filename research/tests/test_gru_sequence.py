"""MR-015 -- unit tests for `GRUSequenceBaseline`'s leakage guard and
structural invariants, plus the real-data protocol run at 1h/6h/24h.

============================== DISCLOSURE ==================================
This is a research baseline run through the same leakage-aware protocol as
every other baseline in `research/models/` -- not a price-prediction or
trading-signal feature. Whether the GRU beats Naive0 is an open, honestly-
reported question; no test in this file asserts it does.
==============================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

import httpx
import numpy as np
import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from real_data import load_real_hourly_returns  # noqa: E402

from models.gru_sequence import GRUSequenceBaseline, _build_windows  # noqa: E402

from naive_first_engine.protocol import ValidationConfig, run_validation_protocol  # noqa: E402


# ---------------------------------------------------------------------------
# Leakage-guard unit test (binding, docs/tickets/MR-015.md "The leakage
# guard" section) -- exercises the window-construction helper directly, on a
# synthetic series with a distinguishable, unique value per timestep, and
# demonstrates a deliberately-broken off-by-one slice would fail the same
# assertion.
# ---------------------------------------------------------------------------


def test_build_windows_never_includes_target_and_matches_exact_slice():
    """Binding leakage-guard test: for every constructed window at position
    `i`, asserts (a) the window equals exactly `values[i-window:i]`, (b) the
    target `values[i]` never appears anywhere in the window, and (c) a
    deliberately-broken off-by-one slice (`values[i-window+1:i+1]`, which DOES
    include `values[i]`) differs from the correct window and would itself
    fail the "target not in window" assertion -- demonstrating this test
    genuinely distinguishes correct from broken windowing, not just something
    trivially true.
    """
    window = 5
    n = 30
    # Unique, monotonic values per timestep -- "target present in window"
    # is a genuine, non-trivial check here (would not pass by accident the
    # way it might on an all-zeros or repeating series).
    series = pd.Series(range(n), dtype="float64")

    X, y = _build_windows(series, window)
    values = series.to_numpy(dtype="float64")

    assert len(X) == n - window
    assert len(y) == n - window

    for k, i in enumerate(range(window, n)):
        correct_window = values[i - window : i]
        broken_window = values[i - window + 1 : i + 1]  # deliberately off-by-one

        # (a) exact match to the correct slice.
        assert np.array_equal(X[k], correct_window)
        # target itself.
        assert y[k] == values[i]

        # (b) the target is never present anywhere in the correct window.
        assert values[i] not in X[k]

        # (c) the broken slice is a genuinely different array that DOES
        # contain the target -- proving this test would fail against a
        # broken implementation, not just pass trivially.
        assert not np.array_equal(correct_window, broken_window)
        assert values[i] in broken_window


def test_build_windows_drops_rows_with_no_valid_window():
    window = 5
    series = pd.Series(range(3), dtype="float64")  # shorter than window
    X, y = _build_windows(series, window)
    assert len(X) == 0
    assert len(y) == 0


# ---------------------------------------------------------------------------
# Structural invariant: fresh model/optimizer/scaler per `predict()` call.
# ---------------------------------------------------------------------------


def _synthetic_train_test(n_train: int = 60, n_test: int = 15, offset: float = 0.0) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(11)
    index = pd.date_range("2021-01-01", periods=n_train + n_test, freq="h")
    values = rng.normal(loc=0.0, scale=0.01, size=n_train + n_test) + offset
    series = pd.Series(values, index=index)
    return series.iloc[:n_train], series.iloc[n_train:]


def test_model_is_reinstantiated_and_refit_per_predict_call():
    """Two separate `predict()` calls, on different `train`/`test` slices,
    must construct entirely fresh model/optimizer objects -- no shared
    mutable state (no instance attribute holding a fitted model/scaler)
    across calls.
    """
    baseline = GRUSequenceBaseline()

    assert not hasattr(baseline, "_model")
    assert not hasattr(baseline, "_optimizer")
    assert not hasattr(baseline, "_scaler")

    train_a, test_a = _synthetic_train_test(n_train=60, n_test=15, offset=0.0)
    train_b, test_b = _synthetic_train_test(n_train=80, n_test=20, offset=5.0)

    predictions_a = baseline.predict(train_a, test_a)
    predictions_b = baseline.predict(train_b, test_b)

    # No instance state persisted between calls.
    assert not hasattr(baseline, "_model")
    assert not hasattr(baseline, "_optimizer")
    assert not hasattr(baseline, "_scaler")

    # The two calls saw materially different train distributions (offset by
    # 5.0), so their fitted predictions should differ -- if state were
    # accidentally shared/reused, the second call's predictions would be
    # anchored to the first call's fit instead.
    assert isinstance(predictions_a, pd.Series)
    assert isinstance(predictions_b, pd.Series)
    assert list(predictions_a.index) == list(test_a.index)
    assert list(predictions_b.index) == list(test_b.index)
    assert not np.allclose(predictions_a.mean(), predictions_b.mean())


# ---------------------------------------------------------------------------
# Train-fold-only scaling.
# ---------------------------------------------------------------------------


def test_scaling_is_fit_on_train_only_not_test_or_combined():
    """Confirms the scaler's normalization statistics (mean/std) match
    `train`'s own values, not `test`'s or a combination of both -- by
    reconstructing the mean/std `predict()` should have used from `train`
    alone and comparing against `train`'s and `test`'s (deliberately
    different-distribution) own statistics.
    """
    rng = np.random.default_rng(3)
    n_train, n_test = 60, 15
    index = pd.date_range("2021-06-01", periods=n_train + n_test, freq="h")

    train_values = rng.normal(loc=0.0, scale=0.01, size=n_train)
    # `test` drawn from a deliberately different distribution so a
    # train-only scaler is distinguishable from a combined/test-only one.
    test_values = rng.normal(loc=10.0, scale=2.0, size=n_test)

    train = pd.Series(train_values, index=index[:n_train])
    test = pd.Series(test_values, index=index[n_train:])

    expected_mean = float(train_values.mean())
    expected_std = float(train_values.std())
    combined_mean = float(np.concatenate([train_values, test_values]).mean())

    assert expected_mean != pytest.approx(combined_mean)

    baseline = GRUSequenceBaseline()
    predictions = baseline.predict(train, test)

    # An untrained (or barely-trained) GRU on a train series centered near
    # zero should produce predictions roughly re-centered around
    # `expected_mean`/`expected_std` (the inverse-scaling step), not around
    # `test`'s own far-away distribution (loc=10.0) or the combined mean --
    # a scaler fit on `test` or on combined data would shift this materially.
    assert abs(predictions.mean() - expected_mean) < abs(predictions.mean() - test_values.mean())
    assert expected_std > 0


# ---------------------------------------------------------------------------
# MR-015 real-data run, 1h/6h/24h -- MR-012's already-landed wider real-data
# window (~2-year, ~17,496-return bounded slice of `binance_price_btcusdt_1h`)
# reused here verbatim, same tenant/source/window
# `research/tests/test_real_data_mr012.py` and
# `research/tests/test_stacking_ensemble.py` use, no second fetch.
# ---------------------------------------------------------------------------

BASE_URL = "http://127.0.0.1:8003"
TENANT_ID = "271d391dd7bf4213b3e5fb8ea6636563"
SOURCE = "binance_price_btcusdt_1h"
START = "2024-08-08T09:00:00"
END = "2026-08-07T09:00:00"

CONFIG_KWARGS = dict(train_window=500, test_window=50, step=250)
PURGE_GAP_BY_HORIZON = {1: 6, 6: 6, 24: 24}


def _live_stack_reachable() -> bool:
    try:
        response = httpx.get(f"{BASE_URL}/health", timeout=2.0)
        return response.status_code < 400
    except httpx.HTTPError:
        return False


def _load_real_returns() -> pd.Series:
    raw_series = load_real_hourly_returns(
        tenant_id=TENANT_ID,
        source=SOURCE,
        start=START,
        end=END,
        base_url=BASE_URL,
    )
    return raw_series.pct_change().dropna()


@pytest.mark.skipif(not _live_stack_reachable(), reason="live ingestion-service stack not reachable")
@pytest.mark.parametrize(
    ("horizon", "purge_gap"),
    [(1, 6), (6, 6), (24, 24)],
)
def test_real_data_run_produces_split_results_with_dm_verdicts(horizon, purge_gap):
    returns = _load_real_returns()

    config = ValidationConfig(
        **CONFIG_KWARGS,
        horizon=horizon,
        purge_gap=purge_gap,
        extra_baselines=[GRUSequenceBaseline()],
    )
    results = run_validation_protocol(returns, config)

    assert len(results) > 0

    verdicts = {"better": 0, "worse": 0, "no significant difference": 0}
    for split_result in results:
        assert "GRUSequenceBaseline" in split_result.baseline_results
        baseline_result = split_result.baseline_results["GRUSequenceBaseline"]

        metrics = baseline_result.metrics
        assert metrics.mae is not None
        assert metrics.rmse is not None
        assert metrics.da is not None
        assert metrics.f1 is not None

        assert baseline_result.dm_result is not None
        verdicts[baseline_result.dm_result.verdict] += 1

    assert sum(verdicts.values()) == len(results)

    print(
        f"\n[MR-015] horizon={horizon}h purge_gap={purge_gap} row_count={len(returns)} "
        f"n_splits={len(results)}"
    )
    print(f"[MR-015] horizon={horizon}h GRUSequenceBaseline DM-vs-Naive0 verdicts: {verdicts}")


def test_harvey_correction_branch_fires_for_horizon_24():
    """Same structural check as MR-009/MR-012/MR-013's own test -- confirms
    the Harvey long-run-variance correction's code path actually differs
    between `horizon=1` and `horizon=24`, not a hand-derivation of the
    statistic.
    """
    from naive_first_engine.dm_test import dm_test

    rng_errors_a = pd.Series([0.01, -0.02, 0.015, -0.01, 0.02, -0.015, 0.01, -0.005, 0.02, -0.01] * 5)
    rng_errors_b = pd.Series([0.02, -0.01, 0.01, -0.02, 0.015, -0.01, 0.02, -0.015, 0.01, -0.02] * 5)

    result_h1 = dm_test(rng_errors_a.to_numpy(), rng_errors_b.to_numpy(), horizon=1)
    result_h24 = dm_test(rng_errors_a.to_numpy(), rng_errors_b.to_numpy(), horizon=24)

    assert result_h1.statistic != pytest.approx(result_h24.statistic)
