"""VS-030: `InlineOrLocalFileDatasetSource`'s optional 3rd `fetched_at`
column/key -- inline dict, inline list-of-rows, and CSV forms -- plus the
"absent column/key is byte-identical to before this ticket" guarantee.
`ObjectStorageDatasetSource` reuses the same parsing (no second parsing
implementation) so it is covered indirectly by `test_dataset_source.py`'s
existing 2-column tests continuing to pass unmodified; this file focuses on
the new 3-column behavior itself.
"""

from __future__ import annotations

import csv
import io

import pandas as pd
import pytest

from app.dataset_source import DatasetSourceError, InlineOrLocalFileDatasetSource


def test_inline_dict_without_fetched_at_key_leaves_fetched_at_none() -> None:
    source = InlineOrLocalFileDatasetSource()
    loaded = source.load(
        {"inline": {"timestamps": ["2024-01-01T00:00:00", "2024-01-01T01:00:00"], "values": [1.0, 2.0]}}
    )
    assert loaded.fetched_at is None
    # Byte-identical series/warnings behavior for the pre-ticket 2-key shape.
    assert list(loaded.series.to_numpy()) == [1.0, 2.0]
    assert loaded.warnings == []


def test_inline_dict_with_fetched_at_key_populates_fetched_at() -> None:
    source = InlineOrLocalFileDatasetSource()
    loaded = source.load(
        {
            "inline": {
                "timestamps": ["2024-01-01T00:00:00", "2024-01-01T01:00:00"],
                "values": [1.0, 2.0],
                "fetched_at": ["2023-12-31T23:00:00", "2024-01-01T00:30:00"],
            }
        }
    )
    assert isinstance(loaded.fetched_at, pd.DatetimeIndex)
    assert list(loaded.fetched_at) == [
        pd.Timestamp("2023-12-31T23:00:00"),
        pd.Timestamp("2024-01-01T00:30:00"),
    ]


def test_inline_list_without_third_element_leaves_fetched_at_none() -> None:
    source = InlineOrLocalFileDatasetSource()
    loaded = source.load(
        {"inline": [["2024-01-01T00:00:00", 1.0], ["2024-01-01T01:00:00", 2.0]]}
    )
    assert loaded.fetched_at is None
    assert list(loaded.series.to_numpy()) == [1.0, 2.0]


def test_inline_list_with_third_element_populates_fetched_at() -> None:
    source = InlineOrLocalFileDatasetSource()
    loaded = source.load(
        {
            "inline": [
                ["2024-01-01T00:00:00", 1.0, "2023-12-31T23:00:00"],
                ["2024-01-01T01:00:00", 2.0, "2024-01-01T00:30:00"],
            ]
        }
    )
    assert isinstance(loaded.fetched_at, pd.DatetimeIndex)
    assert list(loaded.fetched_at) == [
        pd.Timestamp("2023-12-31T23:00:00"),
        pd.Timestamp("2024-01-01T00:30:00"),
    ]


def test_inline_list_mixed_2_and_3_element_rows_raises() -> None:
    source = InlineOrLocalFileDatasetSource()
    with pytest.raises(DatasetSourceError):
        source.load(
            {
                "inline": [
                    ["2024-01-01T00:00:00", 1.0, "2023-12-31T23:00:00"],
                    ["2024-01-01T01:00:00", 2.0],
                ]
            }
        )


def test_csv_without_third_column_leaves_fetched_at_none(tmp_path) -> None:
    path = tmp_path / "two_col.csv"
    path.write_text("2024-01-01T00:00:00,1.0\n2024-01-01T01:00:00,2.0\n", encoding="utf-8")
    source = InlineOrLocalFileDatasetSource()
    loaded = source.load({"path": str(path)})
    assert loaded.fetched_at is None
    assert list(loaded.series.to_numpy()) == [1.0, 2.0]


def test_csv_with_third_column_populates_fetched_at(tmp_path) -> None:
    path = tmp_path / "three_col.csv"
    path.write_text(
        "2024-01-01T00:00:00,1.0,2023-12-31T23:00:00\n"
        "2024-01-01T01:00:00,2.0,2024-01-01T00:30:00\n",
        encoding="utf-8",
    )
    source = InlineOrLocalFileDatasetSource()
    loaded = source.load({"path": str(path)})
    assert isinstance(loaded.fetched_at, pd.DatetimeIndex)
    assert list(loaded.fetched_at) == [
        pd.Timestamp("2023-12-31T23:00:00"),
        pd.Timestamp("2024-01-01T00:30:00"),
    ]


def test_csv_mixed_2_and_3_column_rows_raises(tmp_path) -> None:
    path = tmp_path / "mixed.csv"
    path.write_text(
        "2024-01-01T00:00:00,1.0,2023-12-31T23:00:00\n2024-01-01T01:00:00,2.0\n",
        encoding="utf-8",
    )
    source = InlineOrLocalFileDatasetSource()
    with pytest.raises(DatasetSourceError):
        source.load({"path": str(path)})


def test_object_storage_source_reads_3_column_csv_with_fetched_at() -> None:
    from app.dataset_source import ObjectStorageDatasetSource

    csv_bytes = (
        "2024-01-01T00:00:00,1.0,2023-12-31T23:00:00\n"
        "2024-01-01T01:00:00,2.0,2024-01-01T00:30:00\n"
    ).encode("utf-8")

    class _FakeBody:
        def read(self) -> bytes:
            return csv_bytes

    class _FakeS3Client:
        def get_object(self, Bucket: str, Key: str):
            return {"Body": _FakeBody()}

    source = ObjectStorageDatasetSource(_FakeS3Client(), "bucket")
    loaded = source.load({"object_key": "processed/tenant/x.csv"})
    assert isinstance(loaded.fetched_at, pd.DatetimeIndex)
    assert list(loaded.fetched_at) == [
        pd.Timestamp("2023-12-31T23:00:00"),
        pd.Timestamp("2024-01-01T00:30:00"),
    ]


def test_existing_two_column_inline_test_is_unmodified_and_still_passes() -> None:
    """Rerun of a representative existing 2-column test, unmodified in spirit
    (DH-001's own precedent test shape), proving zero behavior change for
    existing 2-column callers.
    """
    source = InlineOrLocalFileDatasetSource()
    timestamps = ["2024-01-01T01:00:00", "2024-01-01T00:00:00", "2024-01-01T02:00:00"]
    values = [2.0, 1.0, 3.0]
    loaded = source.load({"inline": {"timestamps": timestamps, "values": values}})
    assert list(loaded.series.to_numpy()) == [1.0, 2.0, 3.0]
    assert loaded.warnings == [InlineOrLocalFileDatasetSource.REORDERED_ON_LOAD_WARNING]
    assert loaded.fetched_at is None
