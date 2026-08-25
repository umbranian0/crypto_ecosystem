"""Tests for `DatasetSource` / `InlineOrLocalFileDatasetSource` (VS-005), plus
(VS-015) `ObjectStorageDatasetSource` and `CompositeDatasetSource`.

Confirms inline and local-file modes produce an equivalent series structure
for the same underlying data, and that malformed input raises
`DatasetSourceError` rather than a silently-empty `pd.Series`.

VS-015 additions: `ObjectStorageDatasetSource` is tested against a
hand-rolled fake S3 client (this repo's existing test style favors small,
purpose-built fakes over adding a new test-only dependency like `moto`) that
implements only the single `get_object` method `ObjectStorageDatasetSource`
actually calls. A real-MinIO integration test at the bottom of this file is
gated the same way `test_postgres_repository.py`'s real-Postgres tests are
gated -- skipped, not failed, when no real object storage is reachable at
`OBJECT_STORAGE_ENDPOINT_URL`/`http://localhost:9000`.
"""

from __future__ import annotations

import csv
import io
import os
import uuid

import boto3
import pandas as pd
import pytest
from botocore.exceptions import ClientError

from app.dataset_source import (
    CompositeDatasetSource,
    DatasetSource,
    DatasetSourceError,
    InlineOrLocalFileDatasetSource,
    ObjectStorageDatasetSource,
)

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


# --- ObjectStorageDatasetSource (VS-015) -------------------------------------


def _csv_body(rows: list[list[str]]) -> bytes:
    buffer = io.StringIO()
    writer = csv.writer(buffer)
    for row in rows:
        writer.writerow(row)
    return buffer.getvalue().encode("utf-8")


class _FakeS3Body:
    def __init__(self, data: bytes) -> None:
        self._data = data

    def read(self) -> bytes:
        return self._data


class _FakeS3Client:
    """Hand-rolled fake implementing only the single boto3 client method
    `ObjectStorageDatasetSource` actually calls (`get_object`) -- this repo's
    existing test style (e.g. `InProcessLogEventPublisher`'s own tests)
    favors small purpose-built fakes over a new test-only dependency.
    """

    def __init__(self, objects: dict[tuple[str, str], bytes]) -> None:
        self._objects = objects

    def get_object(self, Bucket: str, Key: str):  # noqa: N803 - matches boto3's own kwarg casing
        key = (Bucket, Key)
        if key not in self._objects:
            raise ClientError(
                {"Error": {"Code": "NoSuchKey", "Message": "The specified key does not exist."}},
                "GetObject",
            )
        return {"Body": _FakeS3Body(self._objects[key])}


def test_object_storage_source_loads_well_formed_csv_object() -> None:
    body = _csv_body(list(zip(_TIMESTAMPS, [str(v) for v in _VALUES])))
    client = _FakeS3Client({("naive-first", "processed/tenant-a/dataset-1.csv"): body})
    source = ObjectStorageDatasetSource(client, "naive-first")

    series = source.load({"object_key": "processed/tenant-a/dataset-1.csv"})

    assert isinstance(series, pd.Series)
    assert isinstance(series.index, pd.DatetimeIndex)
    assert series.index.is_monotonic_increasing
    assert list(series.to_numpy()) == [0.1, 0.2, 0.3]


def test_object_storage_source_matches_inline_source_for_equivalent_data() -> None:
    body = _csv_body(list(zip(_TIMESTAMPS, [str(v) for v in _VALUES])))
    client = _FakeS3Client({("naive-first", "processed/tenant-a/dataset-1.csv"): body})
    object_storage_series = ObjectStorageDatasetSource(client, "naive-first").load(
        {"object_key": "processed/tenant-a/dataset-1.csv"}
    )
    inline_series = InlineOrLocalFileDatasetSource().load(
        {"inline": list(zip(_TIMESTAMPS, _VALUES))}
    )

    pd.testing.assert_series_equal(object_storage_series, inline_series, check_names=False)


def test_object_storage_source_missing_object_raises_dataset_source_error() -> None:
    client = _FakeS3Client({})
    source = ObjectStorageDatasetSource(client, "naive-first")

    with pytest.raises(DatasetSourceError):
        source.load({"object_key": "processed/tenant-a/does-not-exist.csv"})


def test_object_storage_source_malformed_csv_raises_dataset_source_error() -> None:
    # Reuses InlineOrLocalFileDatasetSource._build_series's own
    # non-numeric-value error path (not a re-derived check) --
    # test_malformed_csv_non_numeric_value_raises above proves the same
    # underlying logic for the local-file case; this proves it fires
    # identically for the object-storage case.
    body = _csv_body([["2022-01-01T00:00:00", "oops"]])
    client = _FakeS3Client({("naive-first", "processed/tenant-a/bad.csv"): body})
    source = ObjectStorageDatasetSource(client, "naive-first")

    with pytest.raises(DatasetSourceError):
        source.load({"object_key": "processed/tenant-a/bad.csv"})


def test_object_storage_source_reference_missing_object_key_raises() -> None:
    source = ObjectStorageDatasetSource(_FakeS3Client({}), "naive-first")

    with pytest.raises(DatasetSourceError):
        source.load({"path": "irrelevant"})


def test_object_storage_source_has_no_write_capable_method() -> None:
    # AC3 (read-only): grep-checkable, but also assert it structurally --
    # no put_object/upload_file/delete_object attribute on the class at all.
    for write_method in ("put_object", "upload_file", "delete_object"):
        assert not hasattr(ObjectStorageDatasetSource, write_method)


# --- CompositeDatasetSource (VS-015) -----------------------------------------


def _composite(objects: dict[tuple[str, str], bytes] | None = None) -> CompositeDatasetSource:
    return CompositeDatasetSource(
        InlineOrLocalFileDatasetSource(),
        ObjectStorageDatasetSource(_FakeS3Client(objects or {}), "naive-first"),
    )


def test_composite_routes_inline_reference_to_inline_source() -> None:
    composite = _composite()

    composite_series = composite.load({"inline": list(zip(_TIMESTAMPS, _VALUES))})
    inline_series = InlineOrLocalFileDatasetSource().load(
        {"inline": list(zip(_TIMESTAMPS, _VALUES))}
    )

    pd.testing.assert_series_equal(composite_series, inline_series, check_names=False)


def test_composite_routes_path_reference_to_inline_source(tmp_path) -> None:
    csv_path = tmp_path / "series.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for ts, val in zip(_TIMESTAMPS, _VALUES):
            writer.writerow([ts, val])
    composite = _composite()

    composite_series = composite.load({"path": str(csv_path)})
    inline_series = InlineOrLocalFileDatasetSource().load({"path": str(csv_path)})

    pd.testing.assert_series_equal(composite_series, inline_series, check_names=False)


def test_composite_routes_object_key_reference_to_object_storage_source() -> None:
    body = _csv_body(list(zip(_TIMESTAMPS, [str(v) for v in _VALUES])))
    composite = _composite({("naive-first", "processed/tenant-a/dataset-1.csv"): body})

    series = composite.load({"object_key": "processed/tenant-a/dataset-1.csv"})

    assert list(series.to_numpy()) == [0.1, 0.2, 0.3]


@pytest.mark.parametrize(
    "reference",
    [
        {},
        {"unexpected": "key"},
        "not-a-dict",
    ],
)
def test_composite_unrecognized_reference_raises_dataset_source_error_same_as_today(
    reference,
) -> None:
    composite = _composite()
    plain_inline_source = InlineOrLocalFileDatasetSource()

    with pytest.raises(DatasetSourceError) as composite_exc_info:
        composite.load(reference)
    with pytest.raises(DatasetSourceError) as plain_exc_info:
        plain_inline_source.load(reference)

    assert str(composite_exc_info.value) == str(plain_exc_info.value)


# --- Real-MinIO integration test (VS-015) ------------------------------------

_OBJECT_STORAGE_ENDPOINT_URL = os.environ.get(
    "OBJECT_STORAGE_ENDPOINT_URL", "http://localhost:9000"
)
# Matches infra/.env.example's MINIO_ROOT_USER/MINIO_ROOT_PASSWORD defaults,
# reached via the host-published port (tests run outside Compose).
_MINIO_ACCESS_KEY = os.environ.get("OBJECT_STORAGE_ACCESS_KEY", "naive_first")
_MINIO_SECRET_KEY = os.environ.get("OBJECT_STORAGE_SECRET_KEY", "naive_first_dev_password")
_MINIO_TEST_BUCKET = os.environ.get("OBJECT_STORAGE_BUCKET", "naive-first")


def _minio_reachable() -> bool:
    try:
        client = boto3.client(
            "s3",
            endpoint_url=_OBJECT_STORAGE_ENDPOINT_URL,
            aws_access_key_id=_MINIO_ACCESS_KEY,
            aws_secret_access_key=_MINIO_SECRET_KEY,
        )
        client.list_buckets()
        return True
    except Exception:
        return False


@pytest.mark.skipif(
    not _minio_reachable(),
    reason=f"MinIO not reachable at {_OBJECT_STORAGE_ENDPOINT_URL}",
)
def test_object_storage_source_reads_real_object_from_live_minio() -> None:
    # Test-only write (fixture uploads directly via boto3, not through
    # ObjectStorageDatasetSource, which stays read-only per AC3) against the
    # real running INF-008 MinIO container.
    client = boto3.client(
        "s3",
        endpoint_url=_OBJECT_STORAGE_ENDPOINT_URL,
        aws_access_key_id=_MINIO_ACCESS_KEY,
        aws_secret_access_key=_MINIO_SECRET_KEY,
    )
    existing_buckets = {b["Name"] for b in client.list_buckets().get("Buckets", [])}
    if _MINIO_TEST_BUCKET not in existing_buckets:
        client.create_bucket(Bucket=_MINIO_TEST_BUCKET)

    object_key = f"processed/vs015-test-tenant/{uuid.uuid4().hex}.csv"
    body = _csv_body(list(zip(_TIMESTAMPS, [str(v) for v in _VALUES])))
    client.put_object(Bucket=_MINIO_TEST_BUCKET, Key=object_key, Body=body)
    try:
        source = ObjectStorageDatasetSource(client, _MINIO_TEST_BUCKET)

        series = source.load({"object_key": object_key})

        assert list(series.to_numpy()) == [0.1, 0.2, 0.3]
        assert series.index.is_monotonic_increasing
    finally:
        client.delete_object(Bucket=_MINIO_TEST_BUCKET, Key=object_key)
