"""FastAPI application entry point for economic-service.

Single responsibility: construct the FastAPI app and mount routers. This
mirrors validation-service's/gateway-api's `main.py` shape
(implementation-plan.md section 3).

**Trigger-#11 override disclosure**: this service is scaffolded ahead of its
own build trigger (implementation-plan.md section 6, trigger #11: "only once
a specific client model has already demonstrated stable outperformance in
validation-service"). That trigger has NOT fired. See README.md for the full
disclosure -- this module and everything under `src/app/` is inert scaffolding
until ECON-005's structural eligibility gate is satisfied for real, which it
cannot be today (no real code path in this service can produce a
`source="live"` upstream result -- see ECON-004's mock-only rule).

`GET /health` is upgraded by ECON-002 (in the same PR that adds this
service's DB dependency, per ECON-001 AC3) from a hardcoded `{"status": "ok"}`
placeholder to a real DB-connectivity check, mirroring
validation-service's/gateway-api's OPS-005-01/02 precedent: a cheap
`SELECT 1` against a memoized engine, and a generic `503
{"status": "unhealthy", "detail": "database unreachable"}` on failure with no
raw exception/connection-string leakage.

`POST /simulations` (ECON-005) is the structural eligibility gate -- see
`app.routers.simulations` and `app.eligibility.check_economic_eligibility`.
Wired here the same way `/health`'s dependency is: mounted directly on `app`,
no separate `APIRouter` prefix module needed yet at this service's current
size (mirrors validation-service's own early-stage `main.py` shape before it
grew multiple routers).
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.dependencies.repositories import HealthCheckEngineDep
from app.routers.simulations import router as simulations_router

app = FastAPI(
    title="economic-service",
    description=(
        "Scaffolded skeleton for Subsystem 5 (transaction cost/slippage "
        "simulation). Statistical accuracy != economic value -- see "
        "README.md for the trigger-#11 override disclosure and the "
        "structural eligibility gate that keeps this service inert today."
    ),
    version="0.1.0",
)

app.include_router(simulations_router)


@app.get("/health", response_model=None)
def health(engine: HealthCheckEngineDep) -> dict[str, str] | JSONResponse:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        # OPS-005-01: no raw exception text/connection string/credential in
        # the response body -- a fixed, generic detail string only.
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "detail": "database unreachable"},
        )
    return {"status": "ok"}
