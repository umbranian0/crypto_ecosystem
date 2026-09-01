"""GW-021: operator-gated proxy routes.

Deliberately a new module, not added to runs.py/reports.py/ingestion.py
(the latter belongs to sibling tickets GW-019/GW-020 this sprint) -- this
keeps the file disjoint from all of that sibling work (ticket Design
section).

GET /ingestion/connectors/credentials-status proxies to
ingestion-service's credential-status endpoint (INGEST-004's data),
gated by get_authenticated_operator (GW-021) rather than
get_authenticated_tenant -- this route is not tenant-scoped, it is
operator-only (the concrete consumer this ticket exists to unblock is
DASH-112's operator-facing settings view, not a tenant-facing one).

Handler flow mirrors runs.py/reports.py's existing shape as closely as
that difference allows: resolve Depends(get_authenticated_operator) ->
forward via httpx to INGESTION_SERVICE_URL -> return the response
unmodified in shape and status code. _call_downstream/_raise_for_error
are imported directly from runs.py (GW-009), the same reuse-not-duplicate
precedent reports.py already established for the exact same DRY reason:
extracting them to a shared module would require editing runs.py, which
risks colliding with sibling tickets touching that file this sprint.

INGEST-012 (live-UAT finding, this sprint's UAT addendum): the route this
proxies had been pointed at a downstream path ingestion-service never
built (INGEST-009's crawl-run-status endpoint is a different resource,
not a credentials-presence check) -- ingestion-service now exposes the
real GET /connectors/credentials-status (INGEST-012), so this route
works end-to-end for a valid tenant_id, not just against a mocked
transport as before.

tenant_id (required query parameter, INGEST-012): the caller here is an
operator, who has no TenantContext of their own to source X-Tenant-Id
from (unlike every tenant-authenticated proxy route in runs.py/reports.py/
ingestion.py) -- the operator explicitly names which tenant's credential
status to check. A missing tenant_id is FastAPI's own required-query-param
422, resolved before any downstream call is attempted. Headers are built
by hand here (`{"X-Tenant-Id": tenant_id}`) rather than via
build_downstream_headers (GW-007) -- that helper's signature takes a
TenantContext, which does not exist for an operator caller; reusing it
would mean fabricating a fake TenantContext just to satisfy a type this
caller doesn't actually have, which is worse than the one-line dict here.
This is deliberately narrower than build_downstream_headers (no
X-Correlation-Id) -- extending this route to carry correlation IDs is a
separate, undiscussed change, not part of this ticket's scope.
"""

from __future__ import annotations

from fastapi import APIRouter, Depends, Query

from app.dependencies.http_client import IngestionServiceClientDep
from app.dependencies.operator_auth import get_authenticated_operator
from app.routers.runs import _call_downstream, _raise_for_error

router = APIRouter()


@router.get("/ingestion/connectors/credentials-status")
def get_connectors_credentials_status(
    client: IngestionServiceClientDep,
    tenant_id: str = Query(...),
    _operator: None = Depends(get_authenticated_operator),
) -> dict:
    headers = {"X-Tenant-Id": tenant_id}
    response = _call_downstream(client.get, "/connectors/credentials-status", headers=headers)
    _raise_for_error(response)
    return response.json()
