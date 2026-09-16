"""MR-008 -- minimal `research/`-owned HTTP client for `ingestion-service`'s
existing `GET /datasets/{source}/series` route.

This module exists solely so `research/` can pull a real, tenant-scoped raw
series to feed the same leakage-aware `naive_first_engine` protocol already
exercised on synthetic data by MR-004/MR-005 -- it is NOT a price-prediction
or trading-signal feature, and computes no returns/forecast itself (see
`load_real_hourly_returns`'s own docstring for why the returns transform is
deliberately left to the caller).

Binding "never import `app.*`" rule (CLAUDE.md, docs/tickets/MR-008.md Design
section): this module deliberately does NOT import
`services/validation-service/src/app/dataset_source.py::IngestionServiceDatasetSource`,
even though that class implements the identical HTTP contract -- that class
lives under `services/validation-service`'s own `app` package (service code,
not a shared `libs/*` package), and `research/` may only call another
module's HTTP API, never its app code. This file re-implements only the
minimal request/response handling needed (`GET .../series` -> JSON -> sorted
`pd.Series`), not a copy of `dataset_source.py`'s CSV-parsing logic (which
handles a structurally different two/three-column CSV shape).
"""

from __future__ import annotations

import httpx
import pandas as pd


class RealDataSourceError(RuntimeError):
    """Raised for any non-2xx response or malformed JSON from
    `ingestion-service`'s `GET /datasets/{source}/series` route -- never a
    bare `httpx` exception, and never a silently-empty `pd.Series`.
    """


def load_real_hourly_returns(
    tenant_id: str,
    source: str,
    start: str,
    end: str,
    base_url: str,
    field: str | None = None,
) -> pd.Series:
    """Fetches a tenant-scoped raw series from `ingestion-service` and
    returns it as a sorted `pd.Series` (DatetimeIndex, float values).

    Despite the name (kept for the ticket's own wording), this function does
    NOT compute returns -- it returns the raw level series exactly as
    `ingestion-service` reports it. Computing `.pct_change().dropna()` is the
    caller's own responsibility (see `docs/tickets/MR-008.md`'s Design
    section: "kept separate so the raw-level series is inspectable/testable
    on its own", mirroring `dataset_source.py`'s existing "load a series" vs.
    "what the caller does with it" separation).
    """
    params: dict[str, str] = {"start": start, "end": end}
    if field is not None:
        params["field"] = field

    try:
        response = httpx.get(
            f"{base_url}/datasets/{source}/series",
            params=params,
            headers={"X-Tenant-Id": tenant_id},
            timeout=30.0,
        )
    except httpx.HTTPError as exc:
        raise RealDataSourceError(
            f"could not reach ingestion-service at {base_url!r} for dataset {source!r}: {exc}"
        ) from exc

    if response.status_code >= 400:
        raise RealDataSourceError(
            f"ingestion-service returned {response.status_code} for dataset {source!r}: "
            f"{response.text[:500]}"
        )

    try:
        payload = response.json()
        timestamps = payload["timestamps"]
        values = payload["values"]
    except (ValueError, KeyError, TypeError) as exc:
        raise RealDataSourceError(
            f"malformed response from ingestion-service for dataset {source!r}: {exc}"
        ) from exc

    if not timestamps or not values:
        raise RealDataSourceError(f"dataset {source!r} returned an empty series")

    try:
        index = pd.DatetimeIndex(pd.to_datetime(timestamps, errors="raise"))
        float_values = [float(v) for v in values]
    except (ValueError, TypeError) as exc:
        raise RealDataSourceError(
            f"unparseable timestamp/value in dataset {source!r}: {exc}"
        ) from exc

    series = pd.Series(float_values, index=index, dtype="float64").sort_index()
    return series
