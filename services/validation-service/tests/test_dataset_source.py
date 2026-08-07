"""Tests for `DatasetSource` / `InlineOrLocalFileDatasetSource` (VS-005).

Confirms inline and local-file modes produce an equivalent series structure
for the same underlying data, and that malformed input raises
`DatasetSourceError` rather than a silently-empty `pd.Series`.
"""

from __future__ import annotations

import csv

import pandas as pd
import pytest

from app.dataset_source import DatasetSource, DatasetSourceError, InlineOrLocalFileDatasetSource

_TIMESTAMPS = ["2022-01-01T02:00:00", "2022-01-01T00:00:00", "2022-01-01T01:00:00"]
_VALUES = [0.3, 0.1, 0.2]


def test_inline_list_and_local_file_produce_equivalent_series(tmp_path) -> None:
    source = InlineOrLocalFileDatasetSource()

    inline_series = source.load({"inline": list(zip(_TIMESTAMPS, _VALUES))})

    csv_path = tmp_path / "series.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for ts, val in zip(_TIMESTAMPS, _VALUES):
            writer.writerow([ts, val])
    file_series = source.load({"path": str(csv_path)})

    assert isinstance(inline_series.index, pd.DatetimeIndex)
    assert isinstance(file_series.index, pd.DatetimeIndex)
    assert inline_series.index.is_monotonic_increasing
    assert file_series.index.is_monotonic_increasing
    pd.testing.assert_series_equal(inline_series, file_series, check_names=False)
    assert list(inline_series.to_numpy()) == [0.1, 0.2, 0.3]


def test_inline_dict_shape_matches_inline_list_shape() -> None:
    source = InlineOrLocalFileDatasetSource()

    list_series = source.load({"inline": list(zip(_TIMESTAMPS, _VALUES))})
    dict_series = source.load({"inline": {"timestamps": _TIMESTAMPS, "values": _VALUES}})

    pd.testing.assert_series_equal(list_series, dict_series, check_names=False)


def test_isinstance_check_against_protocol() -> None:
    assert isinstance(InlineOrLocalFileDatasetSource(), DatasetSource)


@pytest.mark.parametrize(
    "reference",
    [
        {},
        {"unexpected": "key"},
        {"inline": [["2022-01-01T00:00:00", "not-a-number"]]},
        {"inline": {"timestamps": ["not-a-timestamp"], "values": [1.0]}},
        {"inline": []},
        {"inline": {"timestamps": [], "values": []}},
        "not-a-dict",
    ],
)
def test_malformed_input_raises_dataset_source_error(reference) -> None:
    source = InlineOrLocalFileDatasetSource()

    with pytest.raises(DatasetSourceError):
        source.load(reference)


def test_missing_local_file_raises_dataset_source_error() -> None:
    source = InlineOrLocalFileDatasetSource()

    with pytest.raises(DatasetSourceError):
        source.load({"path": "/no/such/file/exists.csv"})


def test_malformed_csv_non_numeric_value_raises(tmp_path) -> None:
    csv_path = tmp_path / "bad.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        writer.writerow(["2022-01-01T00:00:00", "oops"])
    source = InlineOrLocalFileDatasetSource()

    with pytest.raises(DatasetSourceError):
        source.load({"path": str(csv_path)})
