"""Tests for the Template Method orchestrator (NFE-014)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from naive_first_engine.protocol import (
    NAIVE0_KEY,
    NAIVE_LAST_KEY,
    ValidationConfig,
    run_validation_protocol,
)
from naive_first_engine.report_schema import SplitResult


def _synthetic_series(n: int = 200, seed: int = 42) -> pd.Series:
    index = pd.date_range("2024-01-01", periods=n, freq="h")
    values = np.random.default_rng(seed).normal(0.0, 1.0, size=n)
    return pd.Series(values, index=index, name="y")


class _AlwaysOne:
    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        return pd.Series(1.0, index=test.index)


def _default_config(**overrides) -> ValidationConfig:
    params = dict(train_window=48, test_window=12, step=12, purge_gap=0, horizon=1)
    params.update(overrides)
    return ValidationConfig(**params)


def test_naive_baselines_always_present_without_extras():
    series = _synthetic_series()
    results = run_validation_protocol(series, _default_config())

    assert len(results) > 0
    for split_result in results:
        assert NAIVE0_KEY in split_result.baseline_results
        assert NAIVE_LAST_KEY in split_result.baseline_results
        assert split_result.baseline_results[NAIVE0_KEY].dm_result is None
        assert split_result.baseline_results[NAIVE_LAST_KEY].dm_result is not None


def test_naive_baselines_always_present_with_extras():
    series = _synthetic_series()
    config = _default_config(extra_baselines=[_AlwaysOne()])
    results = run_validation_protocol(series, config)

    assert len(results) > 0
    for split_result in results:
        assert NAIVE0_KEY in split_result.baseline_results
        assert NAIVE_LAST_KEY in split_result.baseline_results
        assert "_AlwaysOne" in split_result.baseline_results
        assert split_result.baseline_results[NAIVE0_KEY].dm_result is None
        assert split_result.baseline_results["_AlwaysOne"].dm_result is not None


def test_determinism_two_identical_calls_produce_equal_output():
    series = _synthetic_series()
    config = _default_config(extra_baselines=[_AlwaysOne()])

    results_a = run_validation_protocol(series, config)
    results_b = run_validation_protocol(series, config)

    assert len(results_a) == len(results_b)
    for a, b in zip(results_a, results_b):
        assert a.run_id == b.run_id
        assert a.split_index == b.split_index
        assert a.boundaries == b.boundaries
        assert a.baseline_results.keys() == b.baseline_results.keys()
        for key in a.baseline_results:
            assert a.baseline_results[key].metrics == b.baseline_results[key].metrics
            dm_a = a.baseline_results[key].dm_result
            dm_b = b.baseline_results[key].dm_result
            assert dm_a == dm_b


def test_end_to_end_smoke_well_formed_split_results():
    series = _synthetic_series(n=200, seed=7)
    results = run_validation_protocol(series, _default_config())

    assert len(results) > 0
    for i, split_result in enumerate(results):
        assert isinstance(split_result, SplitResult)
        assert split_result.split_index == i
        assert isinstance(split_result.run_id, str) and split_result.run_id != ""
        b = split_result.boundaries
        assert b.train_start <= b.train_end < b.test_start <= b.test_end
        for name, baseline_result in split_result.baseline_results.items():
            m = baseline_result.metrics
            assert m.mae >= 0
            assert m.rmse >= 0
            assert 0 <= m.smape <= 200
            assert 0 <= m.da <= 100
            assert 0 <= m.f1 <= 1


def test_no_shortcut_function_bypasses_orchestrator_for_dm_result():
    """The only public way to get a DMResult populated inside a SplitResult
    is run_validation_protocol; there is no other function in the package
    that goes straight from raw series to a DMResult without replicating the
    full split -> baseline -> metrics -> DM-test sequence by hand.
    """
    import naive_first_engine.protocol as protocol_module

    public_names = [n for n in dir(protocol_module) if not n.startswith("_")]
    callables_besides_entrypoint = [
        n
        for n in public_names
        if n not in {"run_validation_protocol", "ValidationConfig", "NAIVE0_KEY", "NAIVE_LAST_KEY"}
        and callable(getattr(protocol_module, n))
        and getattr(getattr(protocol_module, n), "__module__", "") == protocol_module.__name__
    ]
    assert callables_besides_entrypoint == []


def test_mismatched_config_kind_raises_like_underlying_splitter():
    series = _synthetic_series()
    config = _default_config(train_window=pd.Timedelta(hours=48), step=12)
    with pytest.raises(Exception):
        run_validation_protocol(series, config)
