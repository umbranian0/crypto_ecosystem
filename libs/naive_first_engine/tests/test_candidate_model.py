"""Tests for the additive, multi-column `CandidateModel` interface (MDF-004-01,
ADR-0010). Not wired into `protocol.py` -- these tests exercise the interface
on its own, plus the purge-gap-identical-behavior proof required by the
ticket's Design point 3.
"""

import pandas as pd
import pytest

from naive_first_engine.candidate_model import CandidateModel
from naive_first_engine.splitting import generate_splits


class _FakeCandidateModel:
    """Minimal structural implementation, mirroring test_baselines.py's
    `_FakeBaseline` pattern for `Baseline`."""

    def predict(
        self,
        train_features: pd.DataFrame,
        train_target: pd.Series,
        test_features: pd.DataFrame,
    ) -> pd.Series:
        return pd.Series(0.0, index=test_features.index)


def test_fake_candidate_model_satisfies_the_protocol_structurally():
    fake = _FakeCandidateModel()

    assert isinstance(fake, CandidateModel)


def test_fake_candidate_model_predict_matches_signature():
    train_index = pd.date_range("2024-01-01", periods=3, freq="h")
    test_index = pd.date_range("2024-01-01T03:00", periods=2, freq="h")
    train_features = pd.DataFrame({"a": [1.0, 2.0, 3.0], "b": [4.0, 5.0, 6.0]}, index=train_index)
    train_target = pd.Series([0.1, 0.2, 0.3], index=train_index)
    test_features = pd.DataFrame({"a": [7.0, 8.0], "b": [9.0, 10.0]}, index=test_index)

    result = _FakeCandidateModel().predict(train_features, train_target, test_features)

    assert isinstance(result, pd.Series)
    assert list(result.index) == list(test_index)


def test_candidate_model_predict_cannot_reach_test_target_by_construction():
    # There is no test_target parameter in the CandidateModel.predict
    # signature at all -- confirm the fake's predict call succeeds using
    # only train_features/train_target/test_features, with no test-target
    # argument ever passed or accessible.
    train_index = pd.date_range("2024-01-01", periods=3, freq="h")
    test_index = pd.date_range("2024-01-01T03:00", periods=2, freq="h")
    train_features = pd.DataFrame({"a": [1.0, 2.0, 3.0]}, index=train_index)
    train_target = pd.Series([0.1, 0.2, 0.3], index=train_index)
    test_features = pd.DataFrame({"a": [7.0, 8.0]}, index=test_index)

    import inspect

    signature = inspect.signature(CandidateModel.predict)
    assert list(signature.parameters) == ["self", "train_features", "train_target", "test_features"]

    result = _FakeCandidateModel().predict(train_features, train_target, test_features)
    assert (result == 0.0).all()


def test_generate_splits_same_regardless_of_model_input_shape():
    """MDF-004-01 Design point 3: generate_splits's purge-gap logic is keyed
    off the time index alone, never column count -- the splitter never
    receives model input (Series or DataFrame) at all, only `index`. This
    test proves the *same* `Split` objects come out of `generate_splits`
    whether the caller later slices a univariate Series (Baseline's shape)
    or a multi-column DataFrame (CandidateModel's shape) from those
    boundaries -- generate_splits itself never sees either.
    """
    index = pd.date_range("2024-01-01", periods=200, freq="h")

    splits_for_univariate_caller = generate_splits(
        index, train_window=48, test_window=12, step=12, purge_gap=24
    )
    splits_for_multivariate_caller = generate_splits(
        index, train_window=48, test_window=12, step=12, purge_gap=24
    )

    assert splits_for_univariate_caller == splits_for_multivariate_caller

    # Prove it end-to-end: slicing a Series (Baseline shape) vs. a
    # multi-column DataFrame (CandidateModel shape) from the *same* Split
    # boundaries yields identical purge-gap windows (train_end, test_start)
    # regardless of what is sliced.
    series = pd.Series(range(len(index)), index=index, dtype=float)
    dataframe = pd.DataFrame({"f1": range(len(index)), "f2": range(len(index))}, index=index, dtype=float)

    for split in splits_for_univariate_caller:
        train_series = series.loc[split.train_start : split.train_end]
        train_df = dataframe.loc[split.train_start : split.train_end]
        test_series = series.loc[split.test_start : split.test_end]
        test_df = dataframe.loc[split.test_start : split.test_end]

        assert list(train_series.index) == list(train_df.index)
        assert list(test_series.index) == list(test_df.index)
        # The purge gap itself (train_end -> test_start) is identical
        # regardless of whether one or two columns are sliced from it.
        assert split.train_end < split.test_start
