"""MR-006 -- tests for `research/explainability.py`'s per-split
explainability collectors (`ExplainableLightGBM`, `ExplainableRegimeHMM`).

============================== DISCLOSURE ==================================
Reuses `tests/fixtures.py::synthetic_hourly_returns`, the exact SEEDED,
DETERMINISTIC SYNTHETIC series of 3,000 hourly "returns" MR-004/MR-005's own
tests already use. It is NOT the thesis's real BTC dataset, and no number
produced by these tests is claimed to reproduce, or even approximate, any of
the thesis's published results. These tests exercise the explainability
collector's mechanics -- no second/separate fit, artifact shape for both
model classes, pairing with `run_validation_protocol`'s own `SplitResult`
list -- not a claim that either model predicts real Bitcoin returns,
generates a trading signal, or beats Naive0.
==============================================================================
"""

from __future__ import annotations

import sys
from pathlib import Path

import pandas as pd
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

from explainability import (  # noqa: E402
    ExplainableLightGBM,
    ExplainableRegimeHMM,
    ExplainabilityRecord,
    pair_with_split_results,
)

from naive_first_engine.protocol import ValidationConfig, run_validation_protocol  # noqa: E402

from fixtures import synthetic_hourly_returns as _synthetic_hourly_returns  # noqa: E402

CONFIG_KWARGS = dict(train_window=500, test_window=50, step=250, purge_gap=6)


def test_lightgbm_explainability_reads_off_the_same_fit_no_refit():
    """No second `.fit()` call anywhere in the explainability path: spy on
    `LGBMRegressor.fit` and assert the number of fit calls equals exactly
    the number of splits produced -- one fit per split, not two.
    """
    import lightgbm

    fit_calls: list = []
    original_fit = lightgbm.LGBMRegressor.fit

    def spying_fit(self, *args, **kwargs):
        fit_calls.append(1)
        return original_fit(self, *args, **kwargs)

    lightgbm.LGBMRegressor.fit = spying_fit
    try:
        series = _synthetic_hourly_returns()
        wrapper = ExplainableLightGBM()
        config = ValidationConfig(**CONFIG_KWARGS, horizon=1, extra_baselines=[wrapper])
        results = run_validation_protocol(series, config)
    finally:
        lightgbm.LGBMRegressor.fit = original_fit

    assert len(results) > 0
    assert len(fit_calls) == len(results)  # exactly one fit per split -- no refit
    assert len(wrapper.records) == len(results)

    for record in wrapper.records:
        assert isinstance(record, ExplainabilityRecord)
        assert record.baseline_name == "LightGBMBaseline"
        assert isinstance(record.artifact, pd.Series)
        assert not record.artifact.empty
        assert (record.artifact >= 0).all()  # feature_importances_ are non-negative counts/gains


def test_regime_hmm_explainability_reads_off_the_same_fit_no_refit():
    """No second `.fit()` call anywhere in the explainability path: spy on
    both `GaussianHMM.fit` and `LinearRegression.fit` and assert the HMM is
    fit exactly once per split (not twice) -- the per-state linear fit count
    naturally varies with how many distinct states appear in a given split's
    training fold, so only the HMM count (one fit per split, deterministic)
    is asserted exactly.
    """
    import hmmlearn.hmm as hmm_module

    hmm_fit_calls: list = []
    original_hmm_fit = hmm_module.GaussianHMM.fit

    def spying_hmm_fit(self, X, lengths=None):
        hmm_fit_calls.append(1)
        return original_hmm_fit(self, X, lengths)

    hmm_module.GaussianHMM.fit = spying_hmm_fit
    try:
        series = _synthetic_hourly_returns()
        wrapper = ExplainableRegimeHMM()
        config = ValidationConfig(**CONFIG_KWARGS, horizon=1, extra_baselines=[wrapper])
        results = run_validation_protocol(series, config)
    finally:
        hmm_module.GaussianHMM.fit = original_hmm_fit

    assert len(results) > 0
    assert len(hmm_fit_calls) == len(results)  # exactly one HMM fit per split -- no refit
    assert len(wrapper.records) == len(results)

    for record in wrapper.records:
        assert isinstance(record, ExplainabilityRecord)
        assert record.baseline_name == "RegimeHMMBaseline"
        assert isinstance(record.artifact, dict)
        assert "state_coefficients" in record.artifact
        assert "test_state_assignment" in record.artifact

        state_coefficients = record.artifact["state_coefficients"]
        assert len(state_coefficients) > 0
        for state, payload in state_coefficients.items():
            assert "coef" in payload
            assert "intercept" in payload
            assert "features" in payload

        test_state_assignment = record.artifact["test_state_assignment"]
        assert isinstance(test_state_assignment, pd.Series)
        assert len(test_state_assignment) > 0


@pytest.mark.parametrize(
    "wrapper_cls,horizon",
    [(ExplainableLightGBM, 1), (ExplainableLightGBM, 6), (ExplainableRegimeHMM, 1), (ExplainableRegimeHMM, 6)],
)
def test_pair_with_split_results_matches_by_split_index(wrapper_cls, horizon):
    """Proves the research-side collector pairs each split's existing
    `SplitResult` with its explainability record correctly (AC2's "attaches
    to the existing result path" resolution) -- both model shapes, both
    horizons.
    """
    series = _synthetic_hourly_returns()
    wrapper = wrapper_cls()
    config = ValidationConfig(**CONFIG_KWARGS, horizon=horizon, extra_baselines=[wrapper])
    results = run_validation_protocol(series, config)

    paired = pair_with_split_results(results, wrapper)

    # naive_first_engine.protocol._baseline_key keys config.extra_baselines
    # entries by type(baseline).__name__ (the wrapper class name), not the
    # `.name` attribute -- see baseline_key below.
    baseline_key = type(wrapper).__name__

    assert len(paired) == len(results)
    for split_result, record in paired:
        assert split_result.split_index == record.split_index
        assert baseline_key in split_result.baseline_results
        # The paired SplitResult's own metrics/DM-result are the real,
        # unmodified output of run_validation_protocol -- explainability is
        # additive, not a replacement for the existing report shape.
        baseline_result = split_result.baseline_results[baseline_key]
        assert baseline_result.metrics.mae is not None
        assert baseline_result.dm_result is not None


def test_wrapped_and_unwrapped_baselines_produce_identical_predictions():
    """The wrapper must not change model behavior: `ExplainableLightGBM`'s
    predictions equal plain `LightGBMBaseline`'s predictions on the same
    train/test split (both delegate to the exact same
    `_fit_predict_and_explain` function) -- confirms the explainability path
    is purely additive instrumentation, not a second/different fit.
    """
    from models.gradient_boosting import LightGBMBaseline

    series = _synthetic_hourly_returns()
    train = series.iloc[0:500]
    test = series.iloc[506:556]

    plain_pred = LightGBMBaseline().predict(train, test)
    wrapped_pred = ExplainableLightGBM().predict(train, test)

    # LightGBM with fixed hyperparameters/random_state and identical
    # train/test input is deterministic -- both calls fit independently
    # (each is its own fresh model per the "no state on self" leakage-safety
    # invariant), so exact equality confirms the wrapper's fit logic is
    # genuinely identical to the unwrapped baseline's, not a divergent path.
    pd.testing.assert_series_equal(plain_pred, wrapped_pred)
