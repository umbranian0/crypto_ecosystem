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
"a series came back".

DH-003 additions: a same-timestamp-different-value row (which by
construction can only survive DH-002's exact-duplicate dedup if it differs in
value) now raises `DatasetSourceError` naming the conflicting timestamp and
all distinct values -- a hard failure, never an auto-resolution. Covers: two
rows/different values, two rows/same value (DH-002 handles it, this check
never fires), three rows/three distinct values (all three named).

DH-001 additions: every `DatasetSource.load(...)` call site below now
unpacks `.series` from the returned `LoadedSeries` (the ticket's binding
"uniform across all four classes" contract change) -- assertions on the
underlying series values/index are otherwise unchanged. New tests cover: an
already-sorted input produces `warnings == []`; an out-of-order input
produces the disclosed reordering warning while the output series is still
correctly sorted (behavior unchanged); `CompositeDatasetSource` returns
`LoadedSeries` (not a bare `pd.Series`) for all three reference shapes.
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
    LoadedSeries,
    ObjectStorageDatasetSource,
)

_TIMESTAMPS = ["2022-01-01T02:00:00", "2022-01-01T00:00:00", "2022-01-01T01:00:00"]
_VALUES = [0.3, 0.1, 0.2]

_SORTED_TIMESTAMPS = ["2022-01-01T00:00:00", "2022-01-01T01:00:00", "2022-01-01T02:00:00"]
_SORTED_VALUES = [0.1, 0.2, 0.3]


def test_inline_list_and_local_file_produce_equivalent_series(tmp_path) -> None:
    source = InlineOrLocalFileDatasetSource()

    inline_series = source.load({"inline": list(zip(_TIMESTAMPS, _VALUES))}).series

    csv_path = tmp_path / "series.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for ts, val in zip(_TIMESTAMPS, _VALUES):
            writer.writerow([ts, val])
    file_series = source.load({"path": str(csv_path)}).series

    assert isinstance(inline_series.index, pd.DatetimeIndex)
    assert isinstance(file_series.index, pd.DatetimeIndex)
    assert inline_series.index.is_monotonic_increasing
    assert file_series.index.is_monotonic_increasing
    pd.testing.assert_series_equal(inline_series, file_series, check_names=False)
    assert list(inline_series.to_numpy()) == [0.1, 0.2, 0.3]


def test_inline_dict_shape_matches_inline_list_shape() -> None:
    source = InlineOrLocalFileDatasetSource()

    list_series = source.load({"inline": list(zip(_TIMESTAMPS, _VALUES))}).series
    dict_series = source.load({"inline": {"timestamps": _TIMESTAMPS, "values": _VALUES}}).series

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


# --- DH-001: LoadedSeries / reordering-disclosure -----------------------------


def test_already_sorted_input_produces_no_warning() -> None:
    source = InlineOrLocalFileDatasetSource()

    loaded = source.load({"inline": list(zip(_SORTED_TIMESTAMPS, _SORTED_VALUES))})

    assert isinstance(loaded, LoadedSeries)
    assert loaded.warnings == []
    assert list(loaded.series.to_numpy()) == _SORTED_VALUES
    assert loaded.series.index.is_monotonic_increasing


def test_out_of_order_input_produces_reordering_warning_and_is_still_sorted() -> None:
    source = InlineOrLocalFileDatasetSource()

    loaded = source.load({"inline": list(zip(_TIMESTAMPS, _VALUES))})

    assert isinstance(loaded, LoadedSeries)
    assert loaded.warnings == [InlineOrLocalFileDatasetSource.REORDERED_ON_LOAD_WARNING]
    # Behavior unchanged: the output series is still correctly sorted.
    assert loaded.series.index.is_monotonic_increasing
    assert list(loaded.series.to_numpy()) == _SORTED_VALUES


def test_out_of_order_path_input_also_produces_reordering_warning(tmp_path) -> None:
    csv_path = tmp_path / "unsorted.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for ts, val in zip(_TIMESTAMPS, _VALUES):
            writer.writerow([ts, val])
    source = InlineOrLocalFileDatasetSource()

    loaded = source.load({"path": str(csv_path)})

    assert loaded.warnings == [InlineOrLocalFileDatasetSource.REORDERED_ON_LOAD_WARNING]
    assert loaded.series.index.is_monotonic_increasing


# --- DH-002: exact full-row duplicate detection/dedup ------------------------


def test_one_exact_duplicate_pair_dropped_with_correct_count_warning() -> None:
    source = InlineOrLocalFileDatasetSource()
    # Duplicate inserted already in sorted position (not appended at the
    # end) so this input stays monotonic and does not also trigger DH-001's
    # reordering warning -- that combination is covered separately below.
    timestamps = [
        "2022-01-01T00:00:00",
        "2022-01-01T01:00:00",
        "2022-01-01T01:00:00",
        "2022-01-01T02:00:00",
    ]
    values = [0.1, 0.2, 0.2, 0.3]

    loaded = source.load({"inline": list(zip(timestamps, values))})

    assert loaded.warnings == ["dropped 1 exact-duplicate rows before validation"]
    assert len(loaded.series) == 3
    assert list(loaded.series.to_numpy()) == _SORTED_VALUES


def test_no_duplicates_produces_no_dedup_warning() -> None:
    source = InlineOrLocalFileDatasetSource()

    loaded = source.load({"inline": list(zip(_SORTED_TIMESTAMPS, _SORTED_VALUES))})

    assert loaded.warnings == []
    assert len(loaded.series) == 3


def test_same_timestamp_different_value_is_not_dropped_as_a_duplicate() -> None:
    # DH-002's dedup must NOT silently drop a same-timestamp-different-value
    # row as if it were an exact duplicate -- it is DH-003's job to raise on
    # it instead (see the DH-003 test block below), a hard failure, not a
    # silent drop.
    source = InlineOrLocalFileDatasetSource()
    timestamps = _SORTED_TIMESTAMPS + ["2022-01-01T01:00:00"]
    values = _SORTED_VALUES + [999.0]

    with pytest.raises(DatasetSourceError) as exc_info:
        source.load({"inline": list(zip(timestamps, values))})

    assert "exact-duplicate" not in str(exc_info.value)


def test_reordering_and_duplicate_warnings_coexist_in_order() -> None:
    # Out-of-order fixture (_TIMESTAMPS/_VALUES) plus one exact duplicate row
    # appended -- both DH-001's reordering warning and DH-002's dedup warning
    # must be present, in the order DH-001/DH-002 ran.
    source = InlineOrLocalFileDatasetSource()
    timestamps = _TIMESTAMPS + ["2022-01-01T01:00:00"]
    values = _VALUES + [0.2]

    loaded = source.load({"inline": list(zip(timestamps, values))})

    assert loaded.warnings == [
        InlineOrLocalFileDatasetSource.REORDERED_ON_LOAD_WARNING,
        "dropped 1 exact-duplicate rows before validation",
    ]
    assert list(loaded.series.to_numpy()) == _SORTED_VALUES


# --- DH-003: same-timestamp-different-value conflict, hard failure --------


def test_same_timestamp_different_values_raises_naming_both_values() -> None:
    source = InlineOrLocalFileDatasetSource()
    timestamps = _SORTED_TIMESTAMPS + ["2022-01-01T01:00:00"]
    values = _SORTED_VALUES + [999.0]

    with pytest.raises(DatasetSourceError) as exc_info:
        source.load({"inline": list(zip(timestamps, values))})

    message = str(exc_info.value)
    assert "2022-01-01T01:00:00" in message
    assert "0.2" in message
    assert "999.0" in message


def test_same_timestamp_same_value_does_not_raise_dh003_handled_by_dh002() -> None:
    # Proves DH-002/DH-003 are correctly ordered: an exact duplicate never
    # reaches this check.
    source = InlineOrLocalFileDatasetSource()
    timestamps = [
        "2022-01-01T00:00:00",
        "2022-01-01T01:00:00",
        "2022-01-01T01:00:00",
        "2022-01-01T02:00:00",
    ]
    values = [0.1, 0.2, 0.2, 0.3]

    loaded = source.load({"inline": list(zip(timestamps, values))})

    assert loaded.warnings == ["dropped 1 exact-duplicate rows before validation"]
    assert len(loaded.series) == 3


def test_three_distinct_values_for_one_timestamp_names_all_three() -> None:
    source = InlineOrLocalFileDatasetSource()
    timestamps = ["2022-01-01T00:00:00", "2022-01-01T00:00:00", "2022-01-01T00:00:00"]
    values = [0.1, 0.2, 0.3]

    with pytest.raises(DatasetSourceError) as exc_info:
        source.load({"inline": list(zip(timestamps, values))})

    message = str(exc_info.value)
    assert "0.1" in message
    assert "0.2" in message
    assert "0.3" in message


def test_dedup_runs_before_dh005_split_count_guardrail_post_dedup_count_triggers_422() -> None:
    """Constructs a case where the pre-dedup row count would have produced
    at least 1 split but the post-dedup count produces 0 -- proves
    `runs.py`'s DH-005 guardrail (which calls `generate_splits` on
    `LoadedSeries.series.index`) sees the post-dedup series, not the raw
    input's row count.

    3 distinct hourly timestamps, with the first two each duplicated once
    (raw row count 5). With `train_window=3, test_window=1, purge_gap=0,
    step=1`, the raw (pre-dedup) 5-row index yields >=1 split, but the
    deduped 3-row index -- exactly `train_window + purge_gap + test_window`
    rows, one short of what a 4th row would give -- yields 0 splits.
    """
    from naive_first_engine.splitting import generate_splits

    # Duplicates inserted already in sorted position (not appended at the
    # end) so this input stays monotonic and isolates the dedup effect from
    # DH-001's reordering warning.
    raw_timestamps = [
        "2022-01-01T00:00:00",
        "2022-01-01T00:00:00",
        "2022-01-01T01:00:00",
        "2022-01-01T01:00:00",
        "2022-01-01T02:00:00",
    ]
    raw_values = [0.1, 0.1, 0.2, 0.2, 0.3]
    train_window, test_window, purge_gap, step = 3, 1, 0, 1

    source = InlineOrLocalFileDatasetSource()
    loaded = source.load({"inline": list(zip(raw_timestamps, raw_values))})

    assert loaded.warnings == ["dropped 2 exact-duplicate rows before validation"]
    assert len(loaded.series) == 3

    pre_dedup_index = pd.DatetimeIndex(pd.to_datetime(raw_timestamps)).sort_values()
    pre_dedup_splits = len(
        generate_splits(pre_dedup_index, train_window, test_window, step, purge_gap)
    )
    post_dedup_splits = len(
        generate_splits(loaded.series.index, train_window, test_window, step, purge_gap)
    )

    assert pre_dedup_splits >= 1
    assert post_dedup_splits == 0


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

    loaded = source.load({"object_key": "processed/tenant-a/dataset-1.csv"})

    assert isinstance(loaded, LoadedSeries)
    series = loaded.series
    assert isinstance(series, pd.Series)
    assert isinstance(series.index, pd.DatetimeIndex)
    assert series.index.is_monotonic_increasing
    assert list(series.to_numpy()) == [0.1, 0.2, 0.3]
    # Reordering-detection lives in the shared _build_series helper, which
    # ObjectStorageDatasetSource reuses -- this out-of-order fixture must
    # produce the same disclosed warning here too.
    assert loaded.warnings == [InlineOrLocalFileDatasetSource.REORDERED_ON_LOAD_WARNING]


def test_object_storage_source_matches_inline_source_for_equivalent_data() -> None:
    body = _csv_body(list(zip(_TIMESTAMPS, [str(v) for v in _VALUES])))
    client = _FakeS3Client({("naive-first", "processed/tenant-a/dataset-1.csv"): body})
    object_storage_series = ObjectStorageDatasetSource(client, "naive-first").load(
        {"object_key": "processed/tenant-a/dataset-1.csv"}
    ).series
    inline_series = InlineOrLocalFileDatasetSource().load(
        {"inline": list(zip(_TIMESTAMPS, _VALUES))}
    ).series

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

    loaded = source.load(
        {
            "source": "binance_price",
            "start": "2022-01-01T00:00:00",
            "end": "2022-01-01T03:00:00",
            "field": "close",
        }
    )

    assert isinstance(loaded, LoadedSeries)
    series = loaded.series
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
    ).load({"source": "binance_price"}).series
    inline_series = InlineOrLocalFileDatasetSource().load(
        {"inline": list(zip(_TIMESTAMPS, _VALUES))}
    ).series

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

    tenant_a_series = tenant_a_source.load({"source": "binance_price_btcusdt_1h"}).series
    tenant_b_series = tenant_b_source.load({"source": "binance_price_btcusdt_1h"}).series

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

    composite_loaded = composite.load({"inline": list(zip(_TIMESTAMPS, _VALUES))})
    inline_loaded = InlineOrLocalFileDatasetSource().load(
        {"inline": list(zip(_TIMESTAMPS, _VALUES))}
    )

    assert isinstance(composite_loaded, LoadedSeries)
    pd.testing.assert_series_equal(composite_loaded.series, inline_loaded.series, check_names=False)


def test_composite_routes_path_reference_to_inline_source(tmp_path) -> None:
    csv_path = tmp_path / "series.csv"
    with open(csv_path, "w", newline="", encoding="utf-8") as f:
        writer = csv.writer(f)
        for ts, val in zip(_TIMESTAMPS, _VALUES):
            writer.writerow([ts, val])
    composite = _composite()

    composite_loaded = composite.load({"path": str(csv_path)})
    inline_loaded = InlineOrLocalFileDatasetSource().load({"path": str(csv_path)})

    assert isinstance(composite_loaded, LoadedSeries)
    pd.testing.assert_series_equal(composite_loaded.series, inline_loaded.series, check_names=False)


def test_composite_routes_object_key_reference_to_object_storage_source() -> None:
    body = _csv_body(list(zip(_TIMESTAMPS, [str(v) for v in _VALUES])))
    composite = _composite({("naive-first", "processed/tenant-a/dataset-1.csv"): body})

    loaded = composite.load({"object_key": "processed/tenant-a/dataset-1.csv"})

    assert isinstance(loaded, LoadedSeries)
    assert list(loaded.series.to_numpy()) == [0.1, 0.2, 0.3]


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

    loaded = composite.load({"source": "binance_price"})

    assert isinstance(loaded, LoadedSeries)
    assert list(loaded.series.to_numpy()) == [0.1, 0.2, 0.3]


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

        loaded = source.load({"object_key": object_key})

        assert list(loaded.series.to_numpy()) == [0.1, 0.2, 0.3]
        assert loaded.series.index.is_monotonic_increasing
    finally:
        client.delete_object(Bucket=_MINIO_TEST_BUCKET, Key=object_key)
