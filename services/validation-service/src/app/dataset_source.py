"""`DatasetSource` Adapter interface + interim inline/local-file implementation.

Single responsibility: turn whatever `reference` shape `POST /runs` (VS-006)
passes through into the `pd.Series` (sorted `DatetimeIndex`, float values)
that `naive_first_engine.protocol.run_validation_protocol` expects as its
`series` argument -- see `libs/naive_first_engine/tests/test_regression_1h.py`
for the exact shape those fixtures build.

Interim only: `InlineOrLocalFileDatasetSource` reads either an inline payload
or a local CSV path. A durable, remotely-backed implementation (VS-015) is
blocked on trigger #6 (implementation-plan.md section 6) and will be a
separate class behind the same `DatasetSource` interface -- this module owns
no bucket/prefix scheme belonging to any other service (implementation-plan.md
section 5); that boundary is out of scope here per docs/tickets/VS-005.md's
Analysis section.
"""

from __future__ import annotations

import csv
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
