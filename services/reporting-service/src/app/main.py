"""RS-001: reporting-service FastAPI app entrypoint.

Single responsibility at this ticket: a bare, working FastAPI app skeleton
matching every other service's shape (validation-service/gateway-api/
dashboard-web all have a `src/app/main.py` that mounts routers and exposes
`GET /health`). RS-004/RS-005/RS-006/RS-007 add real routers/health-check
logic; this ticket adds none.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from app.dependencies.repositories import HealthCheckEngineDep
from app.routers import report_generation, report_retrieval

app = FastAPI(title="reporting-service")

# RS-005's router, mounted under /reports. RS-004's report_generation router
# also mounts under /reports -- whichever ticket lands second in this file
# appends its own include_router call rather than removing the other's.
app.include_router(report_retrieval.router, prefix="/reports", tags=["reports"])
app.include_router(report_generation.router, prefix="/reports", tags=["reports"])


@app.get("/health", response_model=None)
def health(engine: HealthCheckEngineDep) -> dict[str, str] | JSONResponse:
    # RS-007: real connectivity check against this service's own `reporting`
    # Postgres schema, mirroring validation-service's `/health`
    # (OPS-005-01) exactly. Redis connectivity (RS-006's subscriber) is
    # explicitly out of scope for this check.
    try:
        with engine.connect() as conn:
            conn.execute(text("SELECT 1"))
    except Exception:
        # No raw exception text/connection string/credential in the
        # response body -- a fixed, generic detail string only.
        return JSONResponse(
            status_code=503,
            content={"status": "unhealthy", "detail": "database unreachable"},
        )
    return {"status": "ok"}
