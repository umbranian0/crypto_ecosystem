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
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter
from sqlalchemy import text

from app.dependencies.http_client import (
    IngestionServiceClientDep,
    ReportingServiceClientDep,
    ValidationServiceClientDep,
)
from app.dependencies.repositories import HealthCheckEngineDep
from app.routers.runs import _call_downstream

router = APIRouter()


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
