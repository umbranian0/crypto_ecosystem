"""FastAPI application entry point for validation-service.

Single responsibility: construct the FastAPI app and mount routers. Business
logic (run execution, persistence, event publishing) lives in routers/,
repositories/, dataset_source.py, events.py -- not here. See README.md for
this service's owns/does-not-own boundary and implementation-plan.md
section 3 for the repo layout this module follows.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.dependencies.repositories import HealthCheckEngineDep
from app.routers import runs, splits

app = FastAPI(
    title="validation-service",
    description="Wraps naive_first_engine as a REST service (see README.md).",
    version="0.1.0",
)

app.include_router(runs.router)
app.include_router(splits.router)


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
