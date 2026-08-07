"""FastAPI application entry point for validation-service.

Single responsibility: construct the FastAPI app and mount routers. Business
logic (run execution, persistence, event publishing) lives in routers/,
repositories/, dataset_source.py, events.py -- not here. See README.md for
this service's owns/does-not-own boundary and implementation-plan.md
section 3 for the repo layout this module follows.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import runs, splits

app = FastAPI(
    title="validation-service",
    description="Wraps naive_first_engine as a REST service (see README.md).",
    version="0.1.0",
)

app.include_router(runs.router)
app.include_router(splits.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
