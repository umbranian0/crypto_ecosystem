"""Tests for `DatasetSource` / `InlineOrLocalFileDatasetSource` (VS-005), plus
(VS-015) `ObjectStorageDatasetSource` and `CompositeDatasetSource`, plus
(VS-023) `IngestionServiceDatasetSource`.

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

VS-023 additions: `IngestionServiceDatasetSource` is tested against
`httpx.MockTransport` (ticket's own test acceptance criteria: never a real
`ingestion-service` call) covering a successful load, a downstream 404, and
a downstream timeout.

VS-024 additions: `IngestionServiceDatasetSource` now takes a required
`tenant_id` constructor argument and sends it as `X-Tenant-Id` on every
outbound call -- `test_ingestion_service_source_sends_x_tenant_id_header`
asserts the header is actually present and correctly valued, and
`test_ingestion_service_source_cross_tenant_isolation_by_actual_value` is the
non-tautological cross-tenant-leak guard (ticket's own Test acceptance
criteria): a single `MockTransport` handler keyed on the inbound
`X-Tenant-Id` header returns two genuinely different response bodies, and the
test asserts on the actual loaded values differing per tenant, not just that
"a series came back" -- it would fail if tenant forwarding were broken or
silently dropped.
"""

from __future__ import annotations

import csv
import io
import os
import uuid

import boto3
import httpx
import pandas as pd
import pytest
from botocore.exceptions import ClientError

from app.dataset_source import (
    CompositeDatasetSource,
    DatasetSource,
    DatasetSourceError,
    IngestionServiceDatasetSource,
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


# --- IngestionServiceDatasetSource (VS-023) ----------------------------------


def _ingestion_client(handler) -> httpx.Client:
    return httpx.Client(
        base_url="http://ingestion-service:8003",
        transport=httpx.MockTransport(handler),
    )


def test_ingestion_service_source_loads_well_formed_response() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/datasets/binance_price/series"
        assert dict(request.url.params) == {
            "start": "2022-01-01T00:00:00",
            "end": "2022-01-01T03:00:00",
            "field": "close",
        }
        return httpx.Response(
            200, json={"timestamps": _TIMESTAMPS, "values": _VALUES}
        )

    client = _ingestion_client(handler)
    source = IngestionServiceDatasetSource(client, "http://ingestion-service:8003", "tenant-a")

    series = source.load(
        {
            "source": "binance_price",
            "start": "2022-01-01T00:00:00",
            "end": "2022-01-01T03:00:00",
            "field": "close",
        }
    )

    assert isinstance(series, pd.Series)
    assert isinstance(series.index, pd.DatetimeIndex)
    assert series.index.is_monotonic_increasing
    assert list(series.to_numpy()) == [0.1, 0.2, 0.3]


def test_ingestion_service_source_matches_inline_source_for_equivalent_data() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"timestamps": _TIMESTAMPS, "values": _VALUES})

    client = _ingestion_client(handler)
    ingestion_series = IngestionServiceDatasetSource(
        client, "http://ingestion-service:8003", "tenant-a"
    ).load({"source": "binance_price"})
    inline_series = InlineOrLocalFileDatasetSource().load(
        {"inline": list(zip(_TIMESTAMPS, _VALUES))}
    )

    pd.testing.assert_series_equal(ingestion_series, inline_series, check_names=False)


def test_ingestion_service_source_omits_absent_optional_params() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert dict(request.url.params) == {}
        return httpx.Response(200, json={"timestamps": _TIMESTAMPS, "values": _VALUES})

    client = _ingestion_client(handler)
    source = IngestionServiceDatasetSource(client, "http://ingestion-service:8003", "tenant-a")

    source.load({"source": "binance_price", "start": None, "end": None, "field": None})


def test_ingestion_service_source_downstream_404_raises_dataset_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "dataset not found"})

    client = _ingestion_client(handler)
    source = IngestionServiceDatasetSource(client, "http://ingestion-service:8003", "tenant-a")

    with pytest.raises(DatasetSourceError):
        source.load({"source": "does-not-exist"})


def test_ingestion_service_source_downstream_timeout_raises_dataset_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    client = _ingestion_client(handler)
    source = IngestionServiceDatasetSource(client, "http://ingestion-service:8003", "tenant-a")

    with pytest.raises(DatasetSourceError):
        source.load({"source": "binance_price"})


def test_ingestion_service_source_malformed_response_raises_dataset_source_error() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"unexpected": "shape"})

    client = _ingestion_client(handler)
    source = IngestionServiceDatasetSource(client, "http://ingestion-service:8003", "tenant-a")

    with pytest.raises(DatasetSourceError):
        source.load({"source": "binance_price"})


def test_ingestion_service_source_reference_missing_source_key_raises() -> None:
    source = IngestionServiceDatasetSource(
        _ingestion_client(lambda request: httpx.Response(200)),
        "http://ingestion-service:8003",
        "tenant-a",
    )

    with pytest.raises(DatasetSourceError):
        source.load({"path": "irrelevant"})


# --- Tenant forwarding (VS-024) -----------------------------------------------


def test_ingestion_service_source_sends_x_tenant_id_header() -> None:
    seen_headers: list[str | None] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen_headers.append(request.headers.get("x-tenant-id"))
        return httpx.Response(200, json={"timestamps": _TIMESTAMPS, "values": _VALUES})

    client = _ingestion_client(handler)
    source = IngestionServiceDatasetSource(client, "http://ingestion-service:8003", "tenant-a")

    source.load({"source": "binance_price_btcusdt_1h"})

    assert seen_headers == ["tenant-a"]


def test_ingestion_service_source_cross_tenant_isolation_by_actual_value() -> None:
    """Non-tautological (VS-024 Test acceptance criteria): a single
    `MockTransport` handler returns genuinely different response bodies keyed
    on the inbound `X-Tenant-Id` header -- the same-named `source` exists for
    both tenants, with different actual values. This test would FAIL if
    tenant forwarding were broken (e.g. no header sent at all, since the
    handler below has no fallback branch and would raise on an unrecognized/
    missing tenant id) or if the wrong tenant's header were sent (the wrong
    tenant's values would come back, silently passing an "a series came back"
    check but failing the exact-value assertions below).
    """
    # Already-ascending timestamps here (unlike the module's shared
    # _TIMESTAMPS fixture) so each tenant's values list below is directly,
    # unambiguously comparable to _build_series's sorted output.
    sorted_timestamps = ["2022-01-01T00:00:00", "2022-01-01T01:00:00", "2022-01-01T02:00:00"]
    tenant_a_values = [0.1, 0.2, 0.3]
    tenant_b_values = [99.0, 98.0, 97.0]

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/datasets/binance_price_btcusdt_1h/series"
        tenant_id = request.headers.get("x-tenant-id")
        if tenant_id == "tenant-a":
            values = tenant_a_values
        elif tenant_id == "tenant-b":
            values = tenant_b_values
        else:
            raise AssertionError(f"unexpected/missing X-Tenant-Id header: {tenant_id!r}")
        return httpx.Response(200, json={"timestamps": sorted_timestamps, "values": values})

    client = _ingestion_client(handler)

    tenant_a_source = IngestionServiceDatasetSource(
        client, "http://ingestion-service:8003", "tenant-a"
    )
    tenant_b_source = IngestionServiceDatasetSource(
        client, "http://ingestion-service:8003", "tenant-b"
    )

    tenant_a_series = tenant_a_source.load({"source": "binance_price_btcusdt_1h"})
    tenant_b_series = tenant_b_source.load({"source": "binance_price_btcusdt_1h"})

    assert list(tenant_a_series.to_numpy()) == [0.1, 0.2, 0.3]
    assert list(tenant_b_series.to_numpy()) == [99.0, 98.0, 97.0]
    assert list(tenant_a_series.to_numpy()) != list(tenant_b_series.to_numpy())


# --- CompositeDatasetSource (VS-015 / VS-023) --------------------------------


def _composite(
    objects: dict[tuple[str, str], bytes] | None = None,
    ingestion_service_source: IngestionServiceDatasetSource | None = None,
) -> CompositeDatasetSource:
    return CompositeDatasetSource(
        InlineOrLocalFileDatasetSource(),
        ObjectStorageDatasetSource(_FakeS3Client(objects or {}), "naive-first"),
        ingestion_service_source,
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


def test_composite_routes_source_reference_to_ingestion_service_source() -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"timestamps": _TIMESTAMPS, "values": _VALUES})

    ingestion_source = IngestionServiceDatasetSource(
        _ingestion_client(handler), "http://ingestion-service:8003", "tenant-a"
    )
    composite = _composite(ingestion_service_source=ingestion_source)

    series = composite.load({"source": "binance_price"})

    assert list(series.to_numpy()) == [0.1, 0.2, 0.3]


def test_composite_without_ingestion_service_source_raises_on_source_reference() -> None:
    composite = _composite()

    with pytest.raises(DatasetSourceError):
        composite.load({"source": "binance_price"})


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
