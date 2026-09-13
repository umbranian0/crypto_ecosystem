"""`DatasetSource` Adapter interface + interim inline/local-file implementation,
plus (VS-015) an object-storage-backed implementation, (VS-023) an
ingestion-service-backed implementation, and a composite that dispatches
between all three.

Single responsibility: turn whatever `reference` shape `POST /runs` (VS-006)
passes through into the `pd.Series` (sorted `DatetimeIndex`, float values)
that `naive_first_engine.protocol.run_validation_protocol` expects as its
`series` argument -- see `libs/naive_first_engine/tests/test_regression_1h.py`
for the exact shape those fixtures build.

`InlineOrLocalFileDatasetSource` reads either an inline payload or a local CSV
path (VS-005). `ObjectStorageDatasetSource` (VS-015) reads a two-column CSV
object from the `processed/{tenant_id}/...` object-storage zone
(solution-design.md section 3.2) via a read-only S3-compatible (MinIO) client
-- it reuses `InlineOrLocalFileDatasetSource._read_csv`/`_build_series`
directly rather than re-deriving CSV parsing (this module's own DRY rule,
implementation-plan.md section 9). `IngestionServiceDatasetSource` (VS-023,
ADR-0005) reads a `{tenant_id, source}` continuous-table time-range slice by
calling `ingestion-service`'s `GET /datasets/{source}/series` directly by
Compose hostname -- never `ingestion.*` tables directly (this module owns no
DB access to another service's schema, implementation-plan.md section 5) --
and reuses `InlineOrLocalFileDatasetSource._build_series` for the JSON
response's timestamp/value parsing, same DRY rule as `ObjectStorageDatasetSource`.
(VS-024) `IngestionServiceDatasetSource` also requires a `tenant_id` at
construction time and sends it as `X-Tenant-Id` on every outbound call, so a
same-named `source` table scoped to a different tenant is never returned --
see that class's own docstring for why this is a constructor argument, not a
`load()` argument.
`CompositeDatasetSource` wraps all three behind the single `DatasetSource`
interface, dispatching on `reference`'s keys at `load()` time, so
`dependencies/repositories.py`'s `get_dataset_source()` can return one object
that serves any shape without `POST /runs`'s handler code ever knowing which
implementation actually served a given call.

This module owns no bucket/prefix scheme belonging to any other service
(implementation-plan.md section 5): it reads whatever object key it's given,
it does not decide what lives at `processed/{tenant_id}/...` or write there --
see this file's `ObjectStorageDatasetSource` docstring. Likewise it owns no
`ingestion.*` table or schema -- see `IngestionServiceDatasetSource`'s
docstring.
"""

from __future__ import annotations

import csv
import dataclasses
import io
import typing

import httpx
import pandas as pd


class DatasetSourceError(ValueError):
    """Raised for any malformed `reference` -- never a silently-empty Series."""


@dataclasses.dataclass(frozen=True)
class LoadedSeries:
    """DH-001: `DatasetSource.load`'s return shape -- the loaded `series`
    itself plus a `warnings` list of any non-fatal, disclosed conditions the
    load produced (e.g. reordering a non-monotonic input). Per CLAUDE.md's
    no-silent-inference rule, any correction a `DatasetSource` implementation
    already makes to a tenant's submitted data (the `.sort_index()` call
    below is not new behavior -- see `_build_series`) must be disclosed, not
    silently applied. All four `DatasetSource` implementations in this module
    return this same shape uniformly (binding on DH-002/DH-003, which extend
    this same contract) -- never a bare `pd.Series`, never a two-tuple only
    some callers learn to unpack.
    """

    series: pd.Series
    warnings: list[str]
    # VS-030: optional per-row `fetched_at` timestamps, same length/order as
    # `series` -- the "when did we actually learn this row's value" clock
    # ADR-0009's alignment rule requires, distinct from `series.index` (the
    # row's own *nominal* timestamp). `None` (default) whenever the source
    # cannot supply it -- see this file's `IngestionServiceDatasetSource`
    # docstring for the one implementation that always leaves this `None`,
    # a disclosed gap, not an oversight.
    fetched_at: pd.DatetimeIndex | None = None


@typing.runtime_checkable
class DatasetSource(typing.Protocol):
    """Adapter interface (implementation-plan.md section 7): one method, so a
    future object-storage-backed source can swap in without touching callers.
    """

    def load(self, reference: object) -> LoadedSeries: ...


class InlineOrLocalFileDatasetSource:
    """Interim `DatasetSource`: `reference` is a dict with either an
    `"inline"` key (list of `[timestamp, value]` pairs, or
    `{"timestamps": [...], "values": [...]}`) or a `"path"` key (local
    filesystem path to a two-column CSV: timestamp, value).
    """

    def load(self, reference: object) -> LoadedSeries:
        if not isinstance(reference, dict):
            raise DatasetSourceError(
                f"reference must be a dict with an 'inline' or 'path' key, got {type(reference)!r}"
            )

        if "inline" in reference:
            timestamps, values, fetched_at = self._parse_inline(reference["inline"])
        elif "path" in reference:
            timestamps, values, fetched_at = self._read_csv(reference["path"])
        else:
            raise DatasetSourceError("reference must contain either an 'inline' or a 'path' key")

        return self._build_series(timestamps, values, fetched_at)

    @staticmethod
    def _parse_inline(inline: object) -> tuple[list, list, list | None]:
        if isinstance(inline, dict):
            if "timestamps" not in inline or "values" not in inline:
                raise DatasetSourceError(
                    "'inline' dict must have 'timestamps' and 'values' keys"
                )
            # VS-030: optional third "fetched_at" key -- absent (the
            # existing 2-key shape) leaves fetched_at as None, byte-identical
            # to pre-ticket behavior for every existing caller.
            fetched_at = list(inline["fetched_at"]) if "fetched_at" in inline else None
            return list(inline["timestamps"]), list(inline["values"]), fetched_at

        if isinstance(inline, list):
            timestamps, values, fetched_at = [], [], []
            has_fetched_at = False
            for row in inline:
                if len(row) == 3:
                    has_fetched_at = True
                elif len(row) != 2:
                    raise DatasetSourceError(
                        f"inline row must be [timestamp, value] or "
                        f"[timestamp, value, fetched_at], got {row!r}"
                    )
                timestamps.append(row[0])
                values.append(row[1])
                fetched_at.append(row[2] if len(row) == 3 else None)
            if not has_fetched_at:
                return timestamps, values, None
            if any(v is None for v in fetched_at):
                raise DatasetSourceError(
                    "inline rows must all carry a 3rd fetched_at element, or none of them"
                )
            return timestamps, values, fetched_at

        raise DatasetSourceError(
            f"'inline' must be a list of [timestamp, value] pairs or a "
            f"{{'timestamps': [...], 'values': [...]}} dict, got {type(inline)!r}"
        )

    @staticmethod
    def _parse_csv_rows(reader: typing.Iterable) -> tuple[list, list, list | None]:
        """Shared 2-or-3-column CSV row parser (VS-030): both the local-file
        path below and `ObjectStorageDatasetSource._read_csv` call this on
        their own `csv.reader(...)` iterator (a file handle and an in-memory
        `io.StringIO`, respectively) -- one parsing implementation, not two.
        """
        timestamps, values, fetched_at = [], [], []
        has_fetched_at = False
        for row in reader:
            if not row:
                continue
            if len(row) == 3:
                has_fetched_at = True
            elif len(row) != 2:
                raise DatasetSourceError(f"CSV row must have 2 or 3 columns, got {row!r}")
            timestamps.append(row[0])
            values.append(row[1])
            fetched_at.append(row[2] if len(row) == 3 else None)
        if not has_fetched_at:
            return timestamps, values, None
        if any(v is None for v in fetched_at):
            raise DatasetSourceError(
                "CSV rows must all carry a 3rd fetched_at column, or none of them"
            )
        return timestamps, values, fetched_at

    @staticmethod
    def _read_csv(path: object) -> tuple[list, list, list | None]:
        try:
            with open(path, newline="", encoding="utf-8") as f:
                return InlineOrLocalFileDatasetSource._parse_csv_rows(csv.reader(f))
        except OSError as exc:
            raise DatasetSourceError(f"could not read CSV at path {path!r}: {exc}") from exc

    #: DH-001: the exact disclosure sentence for a reordered-on-load dataset --
    #: a single shared constant so the string is byte-identical wherever it is
    #: asserted against (this module, dashboard-web's rendering).
    REORDERED_ON_LOAD_WARNING = (
        "dataset rows were not in timestamp order and were sorted before validation"
    )

    @staticmethod
    def _build_series(
        timestamps: list, values: list, fetched_at: list | None = None
    ) -> LoadedSeries:
        if not timestamps or not values:
            raise DatasetSourceError("dataset is empty")

        try:
            index = pd.DatetimeIndex(pd.to_datetime(timestamps, errors="raise"))
        except (ValueError, TypeError) as exc:
            raise DatasetSourceError(f"unparseable timestamp in dataset: {exc}") from exc

        try:
            float_values = [float(v) for v in values]
        except (TypeError, ValueError) as exc:
            raise DatasetSourceError(f"non-numeric value in dataset: {exc}") from exc

        # VS-030: optional third fetched_at column/key, parsed the same way
        # as `timestamps` -- kept as a plain DatetimeIndex-shaped array that
        # travels alongside `series` through the sort/dedup steps below, so
        # each surviving row's fetched_at stays paired with its own
        # timestamp/value. `None` end to end (the pre-ticket path) is
        # byte-identical to before this ticket -- nothing below this branch
        # touches `warnings`/`series` differently when fetched_at is None.
        fetched_at_index: pd.DatetimeIndex | None = None
        if fetched_at is not None:
            try:
                fetched_at_index = pd.DatetimeIndex(pd.to_datetime(fetched_at, errors="raise"))
            except (ValueError, TypeError) as exc:
                raise DatasetSourceError(f"unparseable fetched_at in dataset: {exc}") from exc

        # DH-001: checked *before* the pre-existing .sort_index() call below,
        # which itself is byte-unchanged -- disclosure-only, no change to
        # whether/how sorting happens (ticket Analysis section).
        warnings: list[str] = []
        if not index.is_monotonic_increasing:
            warnings.append(InlineOrLocalFileDatasetSource.REORDERED_ON_LOAD_WARNING)

        sort_order = index.argsort(kind="stable")
        series = pd.Series(float_values, index=index, dtype="float64").iloc[sort_order]
        if fetched_at_index is not None:
            fetched_at_index = fetched_at_index[sort_order]

        if series.empty:
            raise DatasetSourceError("dataset is empty")

        # DH-002: checked *after* DH-001's reordering warning/sort and
        # *before* DH-003's (future) conflict check, per the backlog's
        # required sequencing -- dedup first, conflict-detection on the
        # deduped result second. Duplicates are order-independent here
        # (timestamp AND value both match, so which row is "first" cannot
        # change what the surviving series says) -- comparing post-sort is
        # equivalent to comparing pre-sort.
        pairs = pd.DataFrame({"timestamp": series.index, "value": series.to_numpy()})
        duplicate_mask = pairs.duplicated(keep="first").to_numpy()
        dropped_count = int(duplicate_mask.sum())
        if dropped_count > 0:
            warnings.append(f"dropped {dropped_count} exact-duplicate rows before validation")
            series = series[~duplicate_mask]
            if fetched_at_index is not None:
                fetched_at_index = fetched_at_index[~duplicate_mask]

        # DH-003: runs strictly after DH-002's dedup, on the already-deduped
        # series -- by construction, any timestamp still repeated here must
        # differ in value (an exact match would already have been dropped
        # above), so this is a genuine data conflict, never a mechanical
        # duplicate. Hard failure, no auto-resolution of any kind (not
        # first-wins, not last-wins, not averaged) -- which of two
        # contradictory readings is correct is a judgment call about the
        # user's own data this platform must never make silently.
        conflict_mask = series.index.duplicated(keep=False)
        if conflict_mask.any():
            conflicting_timestamp = series.index[conflict_mask][0]
            distinct_values = (
                series[series.index == conflicting_timestamp].unique().tolist()
            )
            raise DatasetSourceError(
                f"conflicting values for timestamp {conflicting_timestamp.isoformat()}: "
                + " vs ".join(str(v) for v in distinct_values)
            )

        return LoadedSeries(series=series, warnings=warnings, fetched_at=fetched_at_index)


class ObjectStorageDatasetSource:
    """VS-015 `DatasetSource`: `reference` is a dict with an `"object_key"`
    key (e.g. `{"object_key": "processed/{tenant_id}/{dataset_id}.csv"}`)
    naming a two-column CSV object (timestamp, value) in the
    `processed/{tenant_id}/...` object-storage zone (solution-design.md
    section 3.2).

    Read-only by construction: this class has no method that puts, uploads,
    or deletes an object anywhere in the bucket -- it only ever calls the S3
    client's `get_object`. It does not own or provision the bucket/prefix
    scheme; that remains `ingestion-service`'s scope (implementation-plan.md
    section 5) -- see `services/validation-service/README.md`'s VS-015
    section for the explicit "adapter is real, zone population is not
    assumed" caveat this class must not be read past.
    """

    def __init__(self, s3_client: object, bucket: str) -> None:
        self._s3_client = s3_client
        self._bucket = bucket

    def load(self, reference: object) -> LoadedSeries:
        if not isinstance(reference, dict) or "object_key" not in reference:
            raise DatasetSourceError(
                f"reference must be a dict with an 'object_key' key, got {reference!r}"
            )

        object_key = reference["object_key"]
        timestamps, values, fetched_at = self._read_csv(object_key)
        return InlineOrLocalFileDatasetSource._build_series(timestamps, values, fetched_at)

    def _read_csv(self, object_key: str) -> tuple[list, list, list | None]:
        try:
            response = self._s3_client.get_object(Bucket=self._bucket, Key=object_key)
        except Exception as exc:  # noqa: BLE001 - boto3 raises its own botocore.exceptions.ClientError
            raise DatasetSourceError(
                f"could not fetch object {object_key!r} from bucket {self._bucket!r}: {exc}"
            ) from exc

        body = response["Body"].read()
        text_stream = io.StringIO(body.decode("utf-8"))

        # VS-030: delegates row parsing to InlineOrLocalFileDatasetSource's
        # shared `_parse_csv_rows` helper (no second parsing implementation)
        # -- this method keeps only its own S3-fetch step, genuinely specific
        # to this class.
        return InlineOrLocalFileDatasetSource._parse_csv_rows(csv.reader(text_stream))


class IngestionServiceDatasetSource:
    """VS-023 `DatasetSource`, per ADR-0005 ("a dataset is a tenant's
    continuously-growing per-source table, not a discrete per-crawl-run
    snapshot"): `reference` is a dict with a `"source"` key (e.g.
    `{"source": "binance_price", "start": "2022-01-01T00:00:00",
    "end": "2022-02-01T00:00:00", "field": "close"}`, `start`/`end`/`field`
    all optional) naming a continuous per-tenant source table exposed by
    `ingestion-service`'s own `GET /datasets/{source}/series` endpoint
    (`services/ingestion-service/src/app/routers/datasets.py`).

    Calls `ingestion-service` directly by Compose hostname
    (`http://ingestion-service:8003`), never through `gateway-api` (that hop
    is reserved for `dashboard-web`'s external calls) -- the same
    direct-by-hostname precedent `reporting-service` already follows for its
    own call into `validation-service`
    (`services/reporting-service/src/app/dependencies/http_client.py`). This
    class owns no `ingestion.*` table, schema, or ORM model of any kind: the
    tenant scoping and the "does this source exist for this tenant" decision
    live entirely in `ingestion-service`, behind its HTTP contract -- see
    that endpoint's own docstring for why a nonexistent-source and a
    cross-tenant-source both collapse to the same `404`, which this class
    turns into the same `DatasetSourceError` every other `DatasetSource`
    implementation already raises for a downstream failure.

    `tenant_id` (VS-024): required at construction time, not a per-`load()`
    argument, because `load(reference)` is the fixed `DatasetSource` Protocol
    signature every implementation shares -- diverging it here would break
    `CompositeDatasetSource`'s uniform dispatch. Every outbound
    `GET /datasets/{source}/series` call sends it as `X-Tenant-Id`, the same
    header this service's own inbound requests are resolved from
    (`naive_first_common.tenant_context.get_tenant_context`), so
    `ingestion-service` scopes the same-named-but-per-tenant `source` table to
    the caller's own tenant -- without this, `"source"`-keyed references are a
    live cross-tenant data leak (VS-024 Analysis).
    """

    def __init__(self, http_client: httpx.Client, base_url: str, tenant_id: str) -> None:
        self._http_client = http_client
        self._base_url = base_url
        self._tenant_id = tenant_id

    def load(self, reference: object) -> LoadedSeries:
        if not isinstance(reference, dict) or "source" not in reference:
            raise DatasetSourceError(
                f"reference must be a dict with a 'source' key, got {reference!r}"
            )

        source = reference["source"]
        params = {
            key: reference[key]
            for key in ("start", "end", "field")
            if reference.get(key) is not None
        }

        try:
            response = self._http_client.get(
                f"{self._base_url}/datasets/{source}/series",
                params=params,
                headers={"X-Tenant-Id": self._tenant_id},
            )
        except httpx.TimeoutException as exc:
            raise DatasetSourceError(
                f"timed out fetching dataset {source!r} from ingestion-service: {exc}"
            ) from exc
        except httpx.HTTPError as exc:
            raise DatasetSourceError(
                f"could not reach ingestion-service for dataset {source!r}: {exc}"
            ) from exc

        if response.status_code == 404:
            raise DatasetSourceError(
                f"dataset {source!r} not found in ingestion-service for this tenant"
            )
        if response.status_code >= 400:
            raise DatasetSourceError(
                f"ingestion-service returned {response.status_code} for dataset {source!r}"
            )

        try:
            payload = response.json()
            timestamps = payload["timestamps"]
            values = payload["values"]
        except (ValueError, KeyError, TypeError) as exc:
            raise DatasetSourceError(
                f"malformed response from ingestion-service for dataset {source!r}: {exc}"
            ) from exc

        # VS-030: deliberately NOT extended to parse a per-row fetched_at --
        # ingestion-service's own `GET /datasets/{source}/series` response
        # only returns `timestamps`/`values` (it does not expose the
        # per-row `fetched_at` it stores internally; see this ticket's
        # Analysis section / services/validation-service/README.md's VS-030
        # section for the disclosed gap and the follow-up-ticket note). This
        # `LoadedSeries.fetched_at` therefore always stays `None` for this
        # class, which is exactly the signal `feature_dataset.py`'s
        # `FeatureDatasetAssembler` fails closed on for a `{"source": ...}`
        # feature reference, rather than silently approximating alignment
        # using the nominal timestamp.
        return InlineOrLocalFileDatasetSource._build_series(timestamps, values)


class CompositeDatasetSource:
    """VS-015/VS-023: wraps `InlineOrLocalFileDatasetSource`,
    `ObjectStorageDatasetSource`, and (optionally, VS-023)
    `IngestionServiceDatasetSource` behind the single `DatasetSource`
    interface, dispatching on `reference`'s keys at `load()` time --
    `"inline"`/`"path"` route to the interim implementation (unchanged
    behavior), `"object_key"` routes to the object-storage implementation,
    `"source"` routes to the ingestion-service implementation, anything else
    raises the same `DatasetSourceError` shape `InlineOrLocalFileDatasetSource`
    already raised for an unrecognized reference. This is the only class
    `dependencies/repositories.py`'s `get_dataset_source()` returns (AC2:
    `POST /runs`'s handler code never changes, regardless of which
    implementation actually serves a given call).

    `ingestion_service_source` is optional (default `None`) so existing call
    sites/tests that construct this with only the first two sources keep
    working unmodified (VS-023 scope: this file only, wiring
    `dependencies/repositories.py`'s provider to pass a real
    `IngestionServiceDatasetSource` is a separate ticket, VS-024) -- a
    `"source"`-shaped reference against a `CompositeDatasetSource` built
    without one raises `DatasetSourceError` rather than an `AttributeError`.
    """

    def __init__(
        self,
        inline_or_local_file_source: InlineOrLocalFileDatasetSource,
        object_storage_source: ObjectStorageDatasetSource,
        ingestion_service_source: IngestionServiceDatasetSource | None = None,
    ) -> None:
        self._inline_or_local_file_source = inline_or_local_file_source
        self._object_storage_source = object_storage_source
        self._ingestion_service_source = ingestion_service_source

    def load(self, reference: object) -> LoadedSeries:
        if isinstance(reference, dict) and "object_key" in reference:
            return self._object_storage_source.load(reference)
        # VS-023 fourth branch: added ahead of the final delegate below so
        # the three pre-existing branches (this one and the delegate) stay
        # byte-unchanged from VS-015.
        if isinstance(reference, dict) and "source" in reference:
            if self._ingestion_service_source is None:
                raise DatasetSourceError(
                    "reference has a 'source' key but this CompositeDatasetSource "
                    "was not constructed with an IngestionServiceDatasetSource"
                )
            return self._ingestion_service_source.load(reference)
        # Delegates non-object_key shapes (including non-dict/unrecognized
        # references) straight to InlineOrLocalFileDatasetSource.load, which
        # already raises DatasetSourceError with today's exact message shape
        # for both cases -- not re-derived here.
        return self._inline_or_local_file_source.load(reference)
