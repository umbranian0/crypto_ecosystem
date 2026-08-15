"""FastAPI application entry point for gateway-api.

Single responsibility: construct the FastAPI app and mount routers. Business
logic (auth, provisioning, routing) lives in routers/, repositories/,
dependencies/ -- not here. See README.md for this service's owns/does-not-own
boundary and implementation-plan.md section 3 for the repo layout this module
follows. Mirrors validation-service's app.main precedent.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.dependencies.repositories import HealthCheckEngineDep
from app.routers import reports, runs

app = FastAPI(
    title="gateway-api",
    description="The only internet-facing service (see README.md).",
    version="0.1.0",
)

app.include_router(runs.router, tags=["validation-service"])
app.include_router(reports.router, tags=["reporting-service"])


@app.get("/health", response_model=None)
def health(engine: HealthCheckEngineDep) -> dict[str, str] | JSONResponse:
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        # OPS-005-02: no raw exception text/connection string/credential in
        # the response body -- a fixed, generic detail string only, kept
        # consistent with validation-service's own OPS-005-01 body shape.
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "detail": "database unreachable"},
        )
    return {"status": "ok"}
