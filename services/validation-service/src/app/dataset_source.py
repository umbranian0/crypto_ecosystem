"""`DatasetSource` Adapter interface + interim inline/local-file implementation,
plus (VS-015) an object-storage-backed implementation and a composite that
dispatches between the two.

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
implementation-plan.md section 9). `CompositeDatasetSource` wraps both behind
the single `DatasetSource` interface, dispatching on `reference`'s keys at
`load()` time, so `dependencies/repositories.py`'s `get_dataset_source()` can
return one object that serves either shape without `POST /runs`'s handler
code ever knowing which implementation actually served a given call.

This module owns no bucket/prefix scheme belonging to any other service
(implementation-plan.md section 5): it reads whatever object key it's given,
it does not decide what lives at `processed/{tenant_id}/...` or write there --
see this file's `ObjectStorageDatasetSource` docstring.
"""

from __future__ import annotations

import csv
import io
import typing

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


class CompositeDatasetSource:
    """VS-015: wraps `InlineOrLocalFileDatasetSource` and
    `ObjectStorageDatasetSource` behind the single `DatasetSource` interface,
    dispatching on `reference`'s keys at `load()` time -- `"inline"`/`"path"`
    route to the interim implementation (unchanged behavior), `"object_key"`
    routes to the object-storage implementation, anything else raises the
    same `DatasetSourceError` shape `InlineOrLocalFileDatasetSource` already
    raised for an unrecognized reference. This is the only class
    `dependencies/repositories.py`'s `get_dataset_source()` returns (AC2:
    `POST /runs`'s handler code never changes, regardless of which
    implementation actually serves a given call).
    """

    def __init__(
        self,
        inline_or_local_file_source: InlineOrLocalFileDatasetSource,
        object_storage_source: ObjectStorageDatasetSource,
    ) -> None:
        self._inline_or_local_file_source = inline_or_local_file_source
        self._object_storage_source = object_storage_source

    def load(self, reference: object) -> pd.Series:
        if isinstance(reference, dict) and "object_key" in reference:
            return self._object_storage_source.load(reference)
        # Delegates non-object_key shapes (including non-dict/unrecognized
        # references) straight to InlineOrLocalFileDatasetSource.load, which
        # already raises DatasetSourceError with today's exact message shape
        # for both cases -- not re-derived here.
        return self._inline_or_local_file_source.load(reference)
