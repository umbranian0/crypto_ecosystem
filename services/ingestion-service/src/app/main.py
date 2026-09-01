"""INGEST-007: ingestion-service FastAPI app entrypoint.

Single responsibility at this ticket: a bare, working FastAPI app skeleton
matching every other service's shape (validation-service/gateway-api/
reporting-service all have a `src/app/main.py` that mounts routers and
exposes `GET /health`). This is a disclosed override of trigger #6
(implementation-plan.md section 6) -- see README.md's status line. No
pilot-facing routers exist yet; `INGEST-008`/`INGEST-009` add the upload API
and data-quality gate this app will mount.

INGEST-008 mounts `app.routers.connectors`'s `POST /connectors/{source}/run`
below, the same "import router, `app.include_router(...)`" pattern this
docstring already described as the next step.

INGEST-009 (revised) mounts `app.routers.datasets`'s `GET /datasets`,
`GET /datasets/{source}/series`, `GET /connectors/{source}/status` the same
way.
"""

from __future__ import annotations

from fastapi import FastAPI
from fastapi.responses import JSONResponse
from sqlalchemy import text

from naive_first_common import CorrelationIdMiddleware, configure_structured_logging

from app.dependencies.repositories import HealthCheckEngineDep
from app.routers.connectors import router as connectors_router
from app.routers.datasets import router as datasets_router

# OPS-006: configure the shared JSON logging convention before the app is
# constructed -- every log line this process emits picks up the JSON
# formatter and correlation-id filter automatically, no per-call-site change
# needed (same wiring order as validation-service/gateway-api).
configure_structured_logging()

app = FastAPI(
    title="ingestion-service",
    description="Subsystem 2: causal multimodal connectors, upload API, and "
    "data-quality gate (see README.md).",
    version="0.1.0",
)

# OPS-006: reads an inbound X-Correlation-Id (forwarded by gateway-api's
# build_downstream_headers) or generates one, attaches it to every log line
# for this request, and echoes it on the response.
app.add_middleware(CorrelationIdMiddleware)

app.include_router(connectors_router)
app.include_router(datasets_router)


@app.get("/health", response_model=None)
def health(engine: HealthCheckEngineDep) -> dict[str, str] | JSONResponse:
    # OPS-005-01: real connectivity check against this service's own
    # `ingestion` Postgres schema, mirroring validation-service's/
    # reporting-service's `/health` exactly.
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
