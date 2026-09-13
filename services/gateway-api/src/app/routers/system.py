"""GW-022: aggregate `GET /system/health` (minimal slice of `SETUP-020`).

Per the requester's resolution recorded in the ticket's Analysis section,
this pulls only the smallest useful piece of `SETUP-020`'s Monitoring epic --
one aggregate health endpoint. No recent-errors ring buffer, no
run-throughput stats; those remain `SETUP-021`/`SETUP-022`'s own scope, not
duplicated here.

Deliberately a new module, not added to `runs.py`/`reports.py`/`operator.py`
(the latter two belong to sibling tickets `GW-018`/`GW-021`) -- keeps this
file disjoint from all of that (ticket Design section, same precedent
`operator.py` itself just established for the same reason).

`GET /system/health` requires no tenant/operator auth -- health status is
not tenant-scoped or operator-sensitive data (ticket Design section,
explicit call already made for this ticket). It aggregates four independent
checks: this service's own DB connectivity (mirroring `main.py`'s own
`/health` check -- see the note on that duplication below) plus one HTTP
call each to `validation-service`, `reporting-service`, and
`ingestion-service`'s own `/health` endpoints, reusing their existing
`Depends()`-injectable `httpx.Client` providers (`ValidationServiceClientDep`/
`ReportingServiceClientDep`/`IngestionServiceClientDep`, GW-008/GW-018/GW-021)
rather than constructing new ones.

DRY note (ticket Design/DRY-check section): `_call_downstream` is imported
directly from `runs.py` (GW-009), the same reuse-not-duplicate precedent
`reports.py`/`operator.py` already established, for the identical reason --
extracting it to a shared module would require editing `runs.py`, which this
ticket has no need to touch and risks colliding with any sibling ticket that
does. `_service_health_status` below classifies the outcome of that call
into this ticket's three-way status (`"ok"`/`"degraded"`/`"unreachable"`)
rather than reusing `_raise_for_error`, which raises rather than returns --
raising on a single downstream's non-2xx would fail the whole aggregate
call, which is exactly the behavior this ticket's Design section rules out.

Duplication note, called out explicitly rather than left implicit: the
gateway-api-own-DB-connectivity check below (`try: SELECT 1 except: ...`) is
a small, deliberate duplication of `main.py`'s existing `/health` handler
body, not an extraction into a shared helper. Ticket scope is a new,
disjoint router file only -- refactoring `main.py`'s existing `/health`
handler to share a helper with this one is a separate, out-of-scope change
this ticket does not make.

SETUP-022: `GET /system/runs-summary` (same file, a narrow related
"aggregate" concern, consistent placement per this ticket's own Design
section) -- operator-authenticated, cross-tenant validation-run throughput
over a fixed last-24h window. Design judgment call, recorded here per the
ticket's own instruction: `validation-service`'s `GET /runs` is tenant-scoped
(requires `X-Tenant-Id`, resolved server-side from a tenant's own API key on
the normal request path); an operator caller has no tenant API key at all.
Rather than exposing a tenant credential to the operator or touching
`services/validation-service/src/` to add a cross-tenant endpoint (out of
scope for this sprint, full stop), this reuses `TenantRepositoryDep.
list_tenants()` (already used by `tenants.py`, SETUP-011) to enumerate every
tenant gateway-api already knows about, then calls `validation-service`'s
unmodified `GET /runs` once per tenant with a locally-reconstructed
`X-Tenant-Id` header -- valid because `validation-service` trusts
gateway-api's own attestation of tenant identity for every downstream call
(`build_downstream_headers` never forwards a raw tenant API key either, see
`app/dependencies/routing.py`), not because any tenant secret is read or
exposed. See `README.md` for the full writeup, including the per-tenant page
cap and the `"pending"`->`running_pct` status mapping.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone

import httpx
from fastapi import APIRouter, Depends
from pydantic import BaseModel
from sqlalchemy import text

from app.dependencies.http_client import (
    IngestionServiceClientDep,
    ReportingServiceClientDep,
    ValidationServiceClientDep,
)
from app.dependencies.operator_auth import get_authenticated_operator
from app.dependencies.repositories import HealthCheckEngineDep, TenantRepositoryDep
from app.routers.runs import _call_downstream

router = APIRouter()

_RUNS_SUMMARY_WINDOW = timedelta(hours=24)
_RUNS_SUMMARY_PAGE_LIMIT = 100
_RUNS_SUMMARY_MAX_PAGES_PER_TENANT = 5


def _own_health_status(engine) -> str:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        return "unhealthy"
    return "ok"


def _downstream_health_status(client: httpx.Client) -> str:
    """Classifies one downstream `/health` call into this ticket's three-way
    status, reusing GW-009's `_call_downstream` for transport-failure
    detection rather than a second transport-error pattern (ticket Design/
    DRY-check section). A transport-level failure (`_call_downstream`
    translating `httpx.ConnectError`/`httpx.TimeoutException` into a `502`/
    `504` `HTTPException`) maps to `"unreachable"`; a downstream `/health`
    reporting `503` (its own DB unreachable, OPS-005-01/02 shape) maps to
    `"degraded"`, distinct from a transport failure -- neither is allowed to
    raise out of this function, since one bad downstream must not fail the
    whole aggregate call (ticket Implementation acceptance criteria).
    """
    try:
        response = _call_downstream(client.get, "/health")
    except Exception:
        return "unreachable"
    if response.status_code >= 400:
        return "degraded"
    return "ok"


@router.get("/system/health")
def get_system_health(
    engine: HealthCheckEngineDep,
    validation_client: ValidationServiceClientDep,
    reporting_client: ReportingServiceClientDep,
    ingestion_client: IngestionServiceClientDep,
) -> dict[str, str]:
    return {
        "gateway-api": _own_health_status(engine),
        "validation-service": _downstream_health_status(validation_client),
        "reporting-service": _downstream_health_status(reporting_client),
        "ingestion-service": _downstream_health_status(ingestion_client),
    }


class RunsSummaryResponse(BaseModel):
    """SETUP-022: gateway-api-own aggregate shape -- not
    `naive_first_common.contracts`, since this is not a wire contract
    `validation-service` itself emits, just a cross-tenant status-count
    rollup computed here (ticket Design section).
    """

    total: int
    completed_pct: float
    failed_pct: float
    running_pct: float


def _fetch_recent_runs_for_tenant(
    client: httpx.Client, tenant_id: str, window_start: datetime
) -> list[dict]:
    """SETUP-022: fetches one tenant's runs from `validation-service`'s own
    `GET /runs`, reconstructing `X-Tenant-Id` locally (gateway-api already
    knows every tenant id from its own DB via `TenantRepositoryDep`, and
    `validation-service` trusts gateway-api's own attestation of tenant
    identity -- no raw tenant API key is needed or available to an operator
    caller; see this ticket's Design section / README for the full writeup).

    Loops `offset` across pages up to `_RUNS_SUMMARY_MAX_PAGES_PER_TENANT`
    (a disclosed cap bounding worst-case latency at realistic Compose-stack
    data volumes -- a tenant with more than 500 runs in the window will have
    its aggregate undercounted rather than the request stalling indefinitely).
    Stops early once a page's oldest `created_at` falls outside the window,
    since `GET /runs` returns most-recent-first (VS-022).

    One bad/unreachable tenant is skipped (returns whatever was already
    fetched, or an empty list) rather than failing the whole aggregate --
    same "one bad downstream must not fail the whole aggregate" principle
    `_downstream_health_status` above already established in this file.
    """
    headers = {"X-Tenant-Id": tenant_id}
    collected: list[dict] = []

    for page in range(_RUNS_SUMMARY_MAX_PAGES_PER_TENANT):
        offset = page * _RUNS_SUMMARY_PAGE_LIMIT
        try:
            response = _call_downstream(
                client.get,
                "/runs",
                params={"limit": _RUNS_SUMMARY_PAGE_LIMIT, "offset": offset},
                headers=headers,
            )
        except Exception:
            break
        if response.status_code >= 400:
            break

        body = response.json()
        items = body.get("items", [])
        if not items:
            break

        still_in_window = True
        for item in items:
            created_at = datetime.fromisoformat(item["created_at"])
            if created_at.tzinfo is None:
                created_at = created_at.replace(tzinfo=timezone.utc)
            if created_at >= window_start:
                collected.append(item)
            else:
                still_in_window = False

        if not still_in_window or len(items) < _RUNS_SUMMARY_PAGE_LIMIT:
            break

    return collected


@router.get("/system/runs-summary")
def get_runs_summary(
    tenant_repository: TenantRepositoryDep,
    validation_client: ValidationServiceClientDep,
    _operator: None = Depends(get_authenticated_operator),
) -> RunsSummaryResponse:
    """SETUP-022: operator-authenticated, cross-tenant validation-run
    throughput aggregate over a fixed last-24h window (no configurable
    window, per the ticket's "no alerting/threshold" scope constraint).

    Counts only -- no individual run id/tenant/status detail is returned,
    so this endpoint is cross-tenant-safe by construction (Review acceptance
    criteria).

    Status-vocabulary mapping, stated explicitly (see README for the full
    writeup): `validation-service`'s real run status vocabulary today is
    `"pending"`/`"completed"`/`"failed"` -- there is no `"running"` literal
    ever written. `running_pct` below is computed as the `"pending"` count's
    share, the closest honest mapping to the ticket's stated
    `{"running_pct"}` shape.

    Zero runs in the window renders every percentage as `0.0`, never a
    divide-by-zero.
    """
    window_start = datetime.now(timezone.utc) - _RUNS_SUMMARY_WINDOW

    all_runs: list[dict] = []
    for tenant in tenant_repository.list_tenants():
        all_runs.extend(_fetch_recent_runs_for_tenant(validation_client, tenant.id, window_start))

    total = len(all_runs)
    if total == 0:
        return RunsSummaryResponse(
            total=0, completed_pct=0.0, failed_pct=0.0, running_pct=0.0
        )

    completed = sum(1 for run in all_runs if run.get("status") == "completed")
    failed = sum(1 for run in all_runs if run.get("status") == "failed")
    running = sum(1 for run in all_runs if run.get("status") == "pending")

    return RunsSummaryResponse(
        total=total,
        completed_pct=completed / total * 100,
        failed_pct=failed / total * 100,
        running_pct=running / total * 100,
    )
