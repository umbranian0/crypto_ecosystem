"""INGEST-009 (revised): `GET /datasets`, `GET /datasets/{source}/series`,
`GET /connectors/{source}/status` -- tenant-scoped dataset discovery/read API.

Superseded design, per `docs/adr/0005-dataset-is-a-continuous-tenant-source-table.md`
and `docs/solution-design.md` section 8.1/8.3: a dataset is `{tenant_id,
source}` itself -- the ongoing table a tenant's connector appends to -- not a
static, per-id snapshot. There is deliberately no `GET /datasets/{id}` static
lookup anywhere in this module; `GET /datasets/{source}/series` (a range read
over the continuous table) is the only per-source read endpoint. Do not add
a `{id}` shape back in without first re-reading ADR-0005.

Single responsibility: adapt an HTTP request into calls on
`ConnectorRecordRepository`'s three new read methods (`list_datasets`/
`read_series`/`latest_crawl_run`, `app.repositories.interfaces`) -- no
split/table-mapping/aggregate-query logic is reimplemented here; that lives
entirely in `postgres_repository._TABLE_SPECS` and the methods that iterate
it (this ticket's own DRY check: reuses `INGEST-002`'s existing
`(tenant_id, source, event_time)` primary key, no new secondary index or
second per-table dispatch invented).

Field defaults (solution-design.md 8.3, flagged there as open question #2 --
**not yet product-confirmed**, implemented as the working default in the
meantime) -- documented again here and in README.md so neither copy silently
drifts from the other:

| table            | event-time column | default `field` |
|------------------|--------------------|------------------|
| `price_ohlcv`     | `open_time`        | `close`          |
| `onchain_metric`  | `timestamp`        | `value`          |
| `sentiment_score` | `created_utc`      | `reddit_sid_com` |

Cross-tenant / nonexistent `source` collapsing (`GET /datasets/{source}/series`):
`ConnectorRecordRepository.read_series` scopes every query to the calling
`tenant_id` and returns `None` for both "no such source at all" and "source
exists, but only for a different tenant" -- there is no branch here that
could tell the two apart, mirroring `validation-service`'s `GET /runs/{id}`
convention (`app/routers/runs.py`) exactly: a `403`-shaped or otherwise
differently-shaped response for the cross-tenant case would itself leak that
the source exists for someone.

`GET /datasets` never 404s: an empty-history tenant gets `200 {"items": []}`
(`ConnectorRecordRepository.list_datasets` returns `[]`, not `None`, for that
case) -- an empty list is a valid, successful answer, not an error, matching
`validation-service`'s `GET /runs`'s own "empty tenant is 200" precedent.

DRY follow-up (Tech Lead, post-GW-020): `DatasetSummaryResponse` now imports
from `naive_first_common.contracts` (the canonical definition GW-020 added
for gateway-api's proxy) instead of defining a second, hand-duplicated local
copy -- `ingestion-service` already depends on `naive_first_common` for
`TenantContext`/`get_tenant_context`, so this closes the two-definitions gap
GW-020 explicitly flagged rather than silently resolved, per
implementation-plan.md section 9's DRY rule (cross-module duplication belongs
in `libs/*`, not copy-pasted across service boundaries).
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from naive_first_common import TenantContext, get_tenant_context
from naive_first_common.contracts import DatasetSummaryResponse

from app.dependencies.repositories import ConnectorRecordRepositoryDep

router = APIRouter()


class DatasetListResponse(BaseModel):
    items: list[DatasetSummaryResponse]


class SeriesResponse(BaseModel):
    timestamps: list[datetime]
    values: list[float]


class ConnectorStatusResponse(BaseModel):
    status: str
    timestamp: datetime
    row_count: int
    # INGEST-024: `None` for a source that never called `on_progress` (e.g.
    # blockchain.info, or before Binance's first page completes) -- never a
    # fabricated `0`.
    rows_fetched_so_far: int | None = None
    updated_at: datetime | None = None


@router.get("/datasets", response_model=DatasetListResponse)
def list_datasets(
    repository: ConnectorRecordRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> DatasetListResponse:
    summaries = repository.list_datasets(tenant.tenant_id)
    return DatasetListResponse(
        items=[
            DatasetSummaryResponse(
                source=summary.source,
                earliest_timestamp=summary.earliest_timestamp,
                latest_timestamp=summary.latest_timestamp,
                row_count=summary.row_count,
            )
            for summary in summaries
        ]
    )


@router.get("/datasets/{source}/series", response_model=SeriesResponse)
def read_series(
    source: str,
    repository: ConnectorRecordRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
    start: datetime | None = Query(default=None),
    end: datetime | None = Query(default=None),
    field: str | None = Query(default=None),
) -> SeriesResponse:
    # start/end both optional, same code path as the fully-bounded case
    # (ADR-0005): `read_series` itself treats a `None` bound as "no lower/
    # upper filter", not a special-cased "whole dataset" branch here.
    try:
        result = repository.read_series(tenant.tenant_id, source, start, end, field)
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc

    if result is None:
        # Collapsed 404: nonexistent source and cross-tenant source are
        # indistinguishable from this handler's perspective (see module
        # docstring) -- both take this same branch.
        raise HTTPException(status_code=404, detail="dataset not found")

    return SeriesResponse(timestamps=result.timestamps, values=result.values)


@router.get("/connectors/{source}/status", response_model=ConnectorStatusResponse)
def connector_status(
    source: str,
    repository: ConnectorRecordRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> ConnectorStatusResponse:
    summary = repository.latest_crawl_run(tenant.tenant_id, source)
    if summary is None:
        raise HTTPException(status_code=404, detail="no crawl runs recorded for this source")

    return ConnectorStatusResponse(
        status=summary.status,
        timestamp=summary.fetched_at,
        row_count=summary.row_count,
        rows_fetched_so_far=summary.rows_fetched_so_far,
        updated_at=summary.updated_at,
    )
