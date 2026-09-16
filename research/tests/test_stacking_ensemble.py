"""MR-013 -- unit tests for `StackingEnsembleBaseline`'s leakage guard and
structural invariants, plus the real-data protocol run at 1h/6h/24h.

============================== DISCLOSURE ==================================
This is a research baseline run through the same leakage-aware protocol as
every other baseline in `research/models/` -- not a price-prediction or
trading-signal feature. Whether the ensemble beats Naive0 is an open,
honestly-reported question; no test in this file asserts it does.
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

import models.stacking_ensemble as stacking_ensemble_module  # noqa: E402
from models.stacking_ensemble import StackingEnsembleBaseline  # noqa: E402

from naive_first_engine.dm_test import dm_test  # noqa: E402
from naive_first_engine.protocol import ValidationConfig, run_validation_protocol  # noqa: E402


# ---------------------------------------------------------------------------
# Leakage-guard unit test (binding, docs/tickets/MR-013.md "The leakage
# guard" section) -- exercises the in-sample-vs-holdout distinction directly,
# not a trivial "meta-learner has coefficients" assertion.
# ---------------------------------------------------------------------------


class _FakeMemorizingBaseModel:
    """A deliberately overfit fake `Baseline`: if asked to predict rows it
    was "trained" on (its own `train` argument's index), it returns the
    exact true values (perfect in-sample memorization). If asked to predict
    genuinely unseen rows (any row not in `train`'s index), it returns a
    constant 0.0 -- a stand-in for "poor true out-of-sample performance".

    This mirrors a real overfit model: near-perfect in-sample fit, poor
    genuine out-of-sample generalization. Used in place of
    `LightGBMBaseline`/`RegimeHMMBaseline` via monkeypatch to make the
    in-sample-vs-holdout distinction directly observable.
    """

    name = "FakeMemorizingBaseModel"

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        if test.index.isin(train.index).all():
            return train.loc[test.index]
        return pd.Series(0.0, index=test.index)


class _SpyRidge:
    """Records the exact `X`/`y` its `.fit()` was called with, then delegates
    to a real `sklearn.linear_model.Ridge` for `.predict()` so
    `StackingEnsembleBaseline.predict` still returns a valid `pd.Series`.
    """

    last_fit_X: pd.DataFrame | None = None
    last_fit_y: pd.Series | None = None

    def __init__(self, *args, **kwargs):
        from sklearn.linear_model import Ridge

        self._ridge = Ridge(*args, **kwargs)

    def fit(self, X, y):
        _SpyRidge.last_fit_X = X.copy()
        _SpyRidge.last_fit_y = y.copy()
        return self._ridge.fit(X, y)

    def predict(self, X):
        return self._ridge.predict(X)


def _synthetic_train_test(n_train: int = 50, n_test: int = 10) -> tuple[pd.Series, pd.Series]:
    rng = np.random.default_rng(7)
    index = pd.date_range("2021-01-01", periods=n_train + n_test, freq="h")
    values = rng.normal(loc=0.0, scale=0.01, size=n_train + n_test)
    series = pd.Series(values, index=index)
    return series.iloc[:n_train], series.iloc[n_train:]


def test_meta_learner_fits_on_holdout_out_of_sample_predictions_not_in_sample(monkeypatch):
    """Would genuinely FAIL against a naively-in-sample-fit implementation.

    With `_FakeMemorizingBaseModel` standing in for both base models: the
    correct leakage-guard implementation calls
    `.predict(base_fit_portion, meta_fit_holdout_portion)` -- rows the fake
    was never "trained" on -- so the fake returns its poor-out-of-sample
    constant (0.0) for every holdout row, and the meta-learner is fit on
    those all-zero feature columns against the holdout's own real (nonzero)
    target values.

    A naively-in-sample-fit implementation would instead call
    `.predict(base_fit_portion, base_fit_portion)` (or otherwise hand the
    meta-learner predictions on rows the base model was fit on) -- the fake
    would then return the *exact* true values (perfect memorization), so the
    meta-learner would be fit on features that are bit-identical to the
    target, and/or on a target of length `len(base_fit_portion)` instead of
    `len(meta_fit_holdout_portion)`.

    This test asserts the actual `X`/`y` the meta-learner's `.fit()` received
    match the correct (holdout, all-zero-feature) shape, not the buggy
    (in-sample, memorized) shape -- a structural, not cosmetic, check.
    """
    monkeypatch.setattr(stacking_ensemble_module, "LightGBMBaseline", _FakeMemorizingBaseModel)
    monkeypatch.setattr(stacking_ensemble_module, "RegimeHMMBaseline", _FakeMemorizingBaseModel)
    monkeypatch.setattr(stacking_ensemble_module, "Ridge", _SpyRidge)

    train, test = _synthetic_train_test(n_train=50, n_test=10)

    ensemble = StackingEnsembleBaseline()
    ensemble.predict(train, test)

    fit_X = _SpyRidge.last_fit_X
    fit_y = _SpyRidge.last_fit_y
    assert fit_X is not None and fit_y is not None

    expected_holdout_len = len(train) - int(len(train) * 0.8)
    assert len(fit_y) == expected_holdout_len, (
        "meta-learner's y must be the holdout portion's length "
        f"({expected_holdout_len}), not the base-fit portion's length "
        f"({int(len(train) * 0.8)}) -- got {len(fit_y)}. A naively "
        "in-sample-fit implementation would fit on the base-fit portion's "
        "own (larger) length instead."
    )

    # The fake base model only returns real (memorized) values for rows it
    # was "trained" on; since the correct guard hands it genuinely unseen
    # holdout rows, every feature column here must be the fake's
    # poor-out-of-sample constant (0.0) -- never the holdout's own actual
    # (nonzero) return values, which is what an in-sample-fit bug would
    # produce (features bit-identical to the target).
    assert (fit_X["lgbm"] == 0.0).all()
    assert (fit_X["hmm"] == 0.0).all()
    assert not np.allclose(fit_X["lgbm"].to_numpy(), fit_y.to_numpy())

    # The holdout portion's own index (last ~20% of train, in time order) --
    # not the base-fit portion's index -- must be what the meta-learner saw.
    expected_holdout_index = train.index[int(len(train) * 0.8):]
    assert list(fit_y.index) == list(expected_holdout_index)


# ---------------------------------------------------------------------------
# Structural invariant: fresh base-model/meta-learner instances per call.
# ---------------------------------------------------------------------------


def test_base_models_are_reinstantiated_per_predict_call(monkeypatch):
    """Two separate `predict` calls must construct entirely fresh base-model
    instances -- no shared mutable state across calls, matching
    `LightGBMBaseline`/`RegimeHMMBaseline`'s own structural invariant.
    """
    # Keep strong references (not just `id()`s) so CPython can't recycle a
    # freed object's memory address and produce a false "same instance"
    # match -- `instantiated_objects` holds every constructed instance alive
    # for the duration of this test.
    instantiated_objects: list[_FakeMemorizingBaseModel] = []

    class _TrackingFakeBaseModel(_FakeMemorizingBaseModel):
        def __init__(self):
            instantiated_objects.append(self)

    monkeypatch.setattr(stacking_ensemble_module, "LightGBMBaseline", _TrackingFakeBaseModel)
    monkeypatch.setattr(stacking_ensemble_module, "RegimeHMMBaseline", _TrackingFakeBaseModel)

    train_a, test_a = _synthetic_train_test(n_train=50, n_test=10)
    train_b, test_b = _synthetic_train_test(n_train=60, n_test=12)
    # Ensure a genuinely different window for the second call.
    train_b = train_b + 1.0

    ensemble = StackingEnsembleBaseline()
    ensemble.predict(train_a, test_a)
    ensemble.predict(train_b, test_b)

    # 2 base models x 2 fit points (holdout call + full-train call) per
    # predict() call x 2 predict() calls = 8 fresh instances expected.
    assert len(instantiated_objects) == 8
    assert len({id(obj) for obj in instantiated_objects}) == 8

    assert not hasattr(ensemble, "_lgbm")
    assert not hasattr(ensemble, "_hmm")
    assert not hasattr(ensemble, "_meta_learner")


def test_predict_returns_series_matching_test_index():
    train, test = _synthetic_train_test(n_train=200, n_test=20)
    ensemble = StackingEnsembleBaseline()
    predictions = ensemble.predict(train, test)
    assert isinstance(predictions, pd.Series)
    assert list(predictions.index) == list(test.index)


# ---------------------------------------------------------------------------
# MR-013 real-data run, 1h/6h/24h -- MR-012's already-landed, wider real-data
# window (~2-year, ~17,496-return bounded slice of `binance_price_btcusdt_1h`)
# is reused here verbatim, per this ticket's own dispatch note that MR-012
# had already landed by the time this ticket's protocol pass ran -- same
# tenant/source/window `research/tests/test_real_data_mr012.py` uses, no
# second fetch/window derivation.
# ---------------------------------------------------------------------------

BASE_URL = "http://127.0.0.1:8003"
TENANT_ID = "271d391dd7bf4213b3e5fb8ea6636563"
SOURCE = "binance_price_btcusdt_1h"
START = "2024-08-08T09:00:00"
END = "2026-08-07T09:00:00"

CONFIG_KWARGS = dict(train_window=500, test_window=50, step=250)


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
        extra_baselines=[StackingEnsembleBaseline()],
    )
    results = run_validation_protocol(returns, config)

    assert len(results) > 0

    verdicts = {"better": 0, "worse": 0, "no significant difference": 0}
    for split_result in results:
        assert "StackingEnsembleBaseline" in split_result.baseline_results
        baseline_result = split_result.baseline_results["StackingEnsembleBaseline"]

        metrics = baseline_result.metrics
        assert metrics.mae is not None
        assert metrics.rmse is not None
        assert metrics.da is not None
        assert metrics.f1 is not None

        assert baseline_result.dm_result is not None
        verdicts[baseline_result.dm_result.verdict] += 1

    assert sum(verdicts.values()) == len(results)

    print(
        f"\n[MR-013] horizon={horizon}h purge_gap={purge_gap} row_count={len(returns)} "
        f"n_splits={len(results)}"
    )
    print(f"[MR-013] horizon={horizon}h StackingEnsembleBaseline DM-vs-Naive0 verdicts: {verdicts}")


def test_harvey_correction_branch_fires_for_horizon_24():
    """Same structural check as MR-009's own test -- confirms the Harvey
    long-run-variance correction's code path actually differs between
    `horizon=1` and `horizon=24`, not a hand-derivation of the statistic.
    """
    rng_errors_a = pd.Series([0.01, -0.02, 0.015, -0.01, 0.02, -0.015, 0.01, -0.005, 0.02, -0.01] * 5)
    rng_errors_b = pd.Series([0.02, -0.01, 0.01, -0.02, 0.015, -0.01, 0.02, -0.015, 0.01, -0.02] * 5)

    result_h1 = dm_test(rng_errors_a.to_numpy(), rng_errors_b.to_numpy(), horizon=1)
    result_h24 = dm_test(rng_errors_a.to_numpy(), rng_errors_b.to_numpy(), horizon=24)

    assert result_h1.statistic != pytest.approx(result_h24.statistic)
