"""GW-019: tenant-authenticated proxy router forwarding to `ingestion-service`'s
real `POST /connectors/{source}/run` endpoint (INGEST-008).

Deliberately a new module, disjoint from `runs.py`/`reports.py`/`operator.py`/
`system.py` -- keeps this ticket file-collision-free with sibling ticket
`GW-020`, which extends this same new file immediately after this ticket
lands (ticket Design section, binding sequencing constraint).

Unlike `operator.py`'s `GET /ingestion/connectors/credentials-status` (GW-021,
gated by `get_authenticated_operator`), this route is a **tenant** action --
running a connector crawl is something a tenant does for its own data, not an
operator-only concern -- so it resolves `TenantContext` via
`get_authenticated_tenant` (GW-006) and forwards it via `build_downstream_
headers` (GW-007, reused unmodified), the same handler flow `runs.py`/
`reports.py` already established, not `operator.py`'s operator-gated one.

`_call_downstream`/`_raise_for_error` are imported directly from `runs.py`
(GW-009) rather than duplicated or extracted to a shared module -- the same
reuse-not-duplicate precedent `reports.py`/`operator.py` already established,
for the same reason: extracting them would require editing `runs.py`, which
risks colliding with other sprint work touching that file. No circular
import: `runs.py` only imports from `app.dependencies.*`, never from
`app.routers.ingestion`.

The downstream response body/status code (originally `202` success with
`{source, status, row_count, since, fetched_at}`; `404` unknown source; `422`
missing Reddit credentials -- `services/ingestion-service/src/app/routers/
connectors.py`, INGEST-008; see GW-024 below for how this response shape
changed) is forwarded unmodified, not reparsed into a local Pydantic model --
this mirrors `operator.py`'s own `-> dict` pass-through shape rather than
`runs.py`/`reports.py`'s parse-into-local-model shape, since there is no
shared-contract type for this response to hang off of (INGEST-008's
`ConnectorRunResponse` lives in `ingestion-service` only, not
`naive_first_common.contracts`) and this ticket does not add one.

GW-020: `GET /ingestion/datasets` and `GET /ingestion/datasets/{source}/series`
extend this same file (this ticket runs strictly after GW-019's diff lands,
per that ticket's own binding sequencing note -- not concurrently, to avoid a
same-file collision), proxying `ingestion-service`'s real `GET /datasets`/
`GET /datasets/{source}/series` (INGEST-009). Same handler flow as the `POST`
route above: `get_authenticated_tenant` -> `build_downstream_headers` ->
`_call_downstream`/`_raise_for_error` (all reused unmodified, zero new
plumbing). `start`/`end`/`field` query params are forwarded to
`ingestion-service` unmodified -- no re-validation of them happens at this
layer; a bad `field` value's `400` and an unknown-or-cross-tenant `source`'s
collapsed `404` are entirely `ingestion-service`'s own `read_series` behavior
(INGEST-009), forwarded as-is, mirroring `runs.py`'s own "no tenant-isolation
branching added in this router" precedent.

`GET /ingestion/datasets` parses its response into `DatasetListResponse`, an
envelope local to this router wrapping `naive_first_common.contracts.
DatasetSummaryResponse` (GW-020/ARCH-003) -- mirroring `runs.py`'s own
`RunListResponse` wrapping `RunSummaryResponse` precedent exactly, rather
than inventing a different envelope shape. `GET /ingestion/datasets/{source}/
series` stays a plain forwarded dict, matching this file's own `run_connector`
precedent above (`-> dict` pass-through), since a raw timestamps/values
payload has no obvious shared-contract benefit from a typed model.

DASH-109: `GET /ingestion/connectors/{source}/status` extends this same file
(the ticket's own Design section names this exact route as a candidate
addition to "GW-019's proxy" if no proxy for `INGEST-009`'s `GET /connectors/
{source}/status` already existed -- confirmed at implementation time that it
did not). Same handler flow as every other route in this file:
`get_authenticated_tenant` -> `build_downstream_headers` -> `_call_downstream`/
`_raise_for_error`, all reused unmodified. Returns the forwarded
`{status, timestamp, row_count}` body as a plain `dict`, matching
`run_connector`'s own `-> dict` pass-through shape above -- `ingestion-
service`'s `ConnectorStatusResponse` has no shared-contract counterpart in
`naive_first_common.contracts` yet, and this ticket does not add one (its own
scope is `dashboard-web`'s monitoring panel, not a new shared contract type).
The downstream `404` ("no crawl runs recorded for this source", INGEST-009)
is forwarded unmodified -- this router adds no tenant-isolation branching of
its own, same precedent as every other route above.

GW-023: `run_connector` gains an optional `since` query parameter, forwarded
to `ingestion-service` unmodified when supplied (built via the same "drop
`None` entries" idiom `read_series` already established below, not a second
param-building style in this file) and omitted entirely otherwise. `since`'s
actual validation/default-backfill-depth semantics (including the three
rejection reasons behind a downstream `422`) belong to `ingestion-service`
alone (INGEST-013) -- this router adds zero re-validation, matching its own
established "pass-through, ingestion-service owns validation" precedent for
`start`/`end`/`field` on `read_series`.

GW-024: `INGEST-015` changes the downstream `POST /connectors/{source}/run`
contract -- it now returns `202` immediately with `{source, status: "queued",
since, queued_at}` (the crawl itself runs in the background; poll `GET
/ingestion/connectors/{source}/status`, DASH-109 above, for the outcome)
instead of blocking until the crawl finished, and adds a `409` ("crawl
already in progress for connector '<source>'") outcome for a second request
against the same in-flight `(tenant_id, source)` pair. `run_connector` itself
needs no code change for either of these: it already forwards the response
body unmodified as a plain `dict` (no local Pydantic model to go stale), and
`_raise_for_error`'s generic `>= 400` check already forwards any non-2xx
status code, `409` included, with no status-code allowlist to update. Proven,
not just asserted, by
`test_run_connector_forwards_queued_202_response_shape`/
`test_run_connector_conflict_returns_409_forwarded_unmodified` below.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query
from naive_first_common.contracts import DatasetSummaryResponse
from naive_first_common.tenant_context import TenantContext
from pydantic import BaseModel

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.http_client import IngestionServiceClientDep
from app.dependencies.routing import build_downstream_headers
from app.routers.runs import _call_downstream, _raise_for_error

router = APIRouter()


class DatasetListResponse(BaseModel):
    """Response envelope for `GET /ingestion/datasets` (GW-020): mirrors
    `ingestion-service`'s own `DatasetListResponse` envelope field-for-field
    (`services/ingestion-service/src/app/routers/datasets.py`) since this is
    a pass-through proxy, not a reimplementation. `items` uses
    `DatasetSummaryResponse`, imported from `naive_first_common.contracts`
    (GW-020/ARCH-003) -- never redefined here, matching `runs.py`'s
    `RunListResponse`/`RunSummaryResponse` precedent.
    """

    items: list[DatasetSummaryResponse]


@router.post("/ingestion/connectors/{source}/run", status_code=202)
def run_connector(
    source: str,
    client: IngestionServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
    since: str | None = Query(default=None),
) -> dict:
    headers = build_downstream_headers(tenant)
    params = {"since": since} if since is not None else {}
    response = _call_downstream(
        client.post, f"/connectors/{source}/run", params=params, headers=headers
    )
    _raise_for_error(response)
    return response.json()


@router.get("/ingestion/datasets", response_model=DatasetListResponse)
def list_datasets(
    client: IngestionServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
) -> DatasetListResponse:
    headers = build_downstream_headers(tenant)
    response = _call_downstream(client.get, "/datasets", headers=headers)
    _raise_for_error(response)
    return DatasetListResponse(**response.json())


@router.get("/ingestion/datasets/{source}/series")
def read_series(
    source: str,
    client: IngestionServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
    start: str | None = Query(default=None),
    end: str | None = Query(default=None),
    field: str | None = Query(default=None),
) -> dict:
    headers = build_downstream_headers(tenant)
    params = {
        key: value
        for key, value in {"start": start, "end": end, "field": field}.items()
        if value is not None
    }
    response = _call_downstream(
        client.get, f"/datasets/{source}/series", params=params, headers=headers
    )
    _raise_for_error(response)
    return response.json()


@router.get("/ingestion/connectors/{source}/status")
def connector_status(
    source: str,
    client: IngestionServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
) -> dict:
    headers = build_downstream_headers(tenant)
    response = _call_downstream(client.get, f"/connectors/{source}/status", headers=headers)
    _raise_for_error(response)
    return response.json()
