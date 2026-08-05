"""Tests for the Baseline Strategy interface (NFE-004), Naive0 (NFE-005), and
NaiveLast (NFE-006)."""

import pandas as pd
import pytest

from naive_first_engine.baselines import Baseline, Naive0, NaiveLast
from naive_first_engine.metrics import mae

from .fixtures import NAIVE0_MAE_1H, TOLERANCE, build_1h_reference_scenario


class _FakeBaseline:
    """Minimal structural implementation used to confirm the Protocol is usable."""

    def predict(self, train: pd.Series, test: pd.Series) -> pd.Series:
        return pd.Series(0.0, index=test.index)


def test_fake_baseline_satisfies_the_protocol_structurally():
    fake = _FakeBaseline()

    assert isinstance(fake, Baseline)


def test_fake_baseline_predict_matches_signature():
    train = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3, freq="h"))
    test = pd.Series([4.0, 5.0], index=pd.date_range("2024-01-01T03:00", periods=2, freq="h"))

    result = _FakeBaseline().predict(train, test)

    assert isinstance(result, pd.Series)
    assert list(result.index) == list(test.index)


def test_naive0_satisfies_the_baseline_protocol():
    assert isinstance(Naive0(), Baseline)


def test_naive0_predict_is_zero_indexed_like_test():
    train = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3, freq="h"))
    test = pd.Series([4.0, 5.0], index=pd.date_range("2024-01-01T03:00", periods=2, freq="h"))

    result = Naive0().predict(train, test)

    assert isinstance(result, pd.Series)
    assert list(result.index) == list(test.index)
    assert (result == 0.0).all()


def test_naive0_predict_ignores_test_values_and_train_entirely():
    train = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3, freq="h"))
    index = pd.date_range("2024-01-01T03:00", periods=2, freq="h")
    test_a = pd.Series([4.0, 5.0], index=index)
    test_b = pd.Series([-999.0, 1234.5], index=index)

    result_a = Naive0().predict(train, test_a)
    result_b = Naive0().predict(train, test_b)

    pd.testing.assert_series_equal(result_a, result_b)


def test_naive0_regression_matches_thesis_1h_mae():
    scenario = build_1h_reference_scenario()

    naive0_forecast = Naive0().predict(train=scenario.y_true, test=scenario.y_true)

    assert mae(scenario.y_true, naive0_forecast) == pytest.approx(NAIVE0_MAE_1H, abs=TOLERANCE)


def test_naivelast_satisfies_the_baseline_protocol():
    assert isinstance(NaiveLast(), Baseline)


def test_naivelast_predict_is_constant_and_equals_last_train_value():
    train = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3, freq="h"))
    test = pd.Series([4.0, 5.0], index=pd.date_range("2024-01-01T03:00", periods=2, freq="h"))

    result = NaiveLast().predict(train, test)

    assert isinstance(result, pd.Series)
    assert list(result.index) == list(test.index)
    assert (result == 3.0).all()


def test_naivelast_differs_from_naive0_when_last_train_value_is_nonzero():
    train = pd.Series([1.0, 2.0, 3.0], index=pd.date_range("2024-01-01", periods=3, freq="h"))
    test = pd.Series([4.0, 5.0], index=pd.date_range("2024-01-01T03:00", periods=2, freq="h"))

    naivelast_result = NaiveLast().predict(train, test)
    naive0_result = Naive0().predict(train, test)

    assert train.iloc[-1] != 0.0
    assert not naivelast_result.equals(naive0_result)
