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
import io
import typing

import httpx
import pandas as pd


class DatasetSourceError(ValueError):
    """Raised for any malformed `reference` -- never a silently-empty Series."""


@typing.runtime_checkable
class DatasetSource(typing.Protocol):
    """Adapter interface (implementation-plan.md section 7): one method, so a
    future object-storage-backed source can swap in without touching callers.
    """

    def load(self, reference: object) -> pd.Series: ...


class InlineOrLocalFileDatasetSource:
    """Interim `DatasetSource`: `reference` is a dict with either an
    `"inline"` key (list of `[timestamp, value]` pairs, or
    `{"timestamps": [...], "values": [...]}`) or a `"path"` key (local
    filesystem path to a two-column CSV: timestamp, value).
    """

    def load(self, reference: object) -> pd.Series:
        if not isinstance(reference, dict):
            raise DatasetSourceError(
                f"reference must be a dict with an 'inline' or 'path' key, got {type(reference)!r}"
            )

        if "inline" in reference:
            timestamps, values = self._parse_inline(reference["inline"])
        elif "path" in reference:
            timestamps, values = self._read_csv(reference["path"])
        else:
            raise DatasetSourceError("reference must contain either an 'inline' or a 'path' key")

        return self._build_series(timestamps, values)

    @staticmethod
    def _parse_inline(inline: object) -> tuple[list, list]:
        if isinstance(inline, dict):
            if "timestamps" not in inline or "values" not in inline:
                raise DatasetSourceError(
                    "'inline' dict must have 'timestamps' and 'values' keys"
                )
            return list(inline["timestamps"]), list(inline["values"])

        if isinstance(inline, list):
            timestamps, values = [], []
            for row in inline:
                if len(row) != 2:
                    raise DatasetSourceError(f"inline row must be [timestamp, value], got {row!r}")
                timestamps.append(row[0])
                values.append(row[1])
            return timestamps, values

        raise DatasetSourceError(
            f"'inline' must be a list of [timestamp, value] pairs or a "
            f"{{'timestamps': [...], 'values': [...]}} dict, got {type(inline)!r}"
        )

    @staticmethod
    def _read_csv(path: object) -> tuple[list, list]:
        timestamps, values = [], []
        try:
            with open(path, newline="", encoding="utf-8") as f:
                for row in csv.reader(f):
                    if not row:
                        continue
                    if len(row) != 2:
                        raise DatasetSourceError(f"CSV row must have 2 columns, got {row!r}")
                    timestamps.append(row[0])
                    values.append(row[1])
        except OSError as exc:
            raise DatasetSourceError(f"could not read CSV at path {path!r}: {exc}") from exc
        return timestamps, values

    @staticmethod
    def _build_series(timestamps: list, values: list) -> pd.Series:
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

        series = pd.Series(float_values, index=index, dtype="float64").sort_index()

        if series.empty:
            raise DatasetSourceError("dataset is empty")

        return series


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

    def load(self, reference: object) -> pd.Series:
        if not isinstance(reference, dict) or "object_key" not in reference:
            raise DatasetSourceError(
                f"reference must be a dict with an 'object_key' key, got {reference!r}"
            )

        object_key = reference["object_key"]
        timestamps, values = self._read_csv(object_key)
        return InlineOrLocalFileDatasetSource._build_series(timestamps, values)

    def _read_csv(self, object_key: str) -> tuple[list, list]:
        try:
            response = self._s3_client.get_object(Bucket=self._bucket, Key=object_key)
        except Exception as exc:  # noqa: BLE001 - boto3 raises its own botocore.exceptions.ClientError
            raise DatasetSourceError(
                f"could not fetch object {object_key!r} from bucket {self._bucket!r}: {exc}"
            ) from exc

        body = response["Body"].read()
        text_stream = io.StringIO(body.decode("utf-8"))

        timestamps, values = [], []
        for row in csv.reader(text_stream):
            if not row:
                continue
            if len(row) != 2:
                raise DatasetSourceError(f"CSV row must have 2 columns, got {row!r}")
            timestamps.append(row[0])
            values.append(row[1])
        return timestamps, values


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

    def load(self, reference: object) -> pd.Series:
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

    def load(self, reference: object) -> pd.Series:
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
