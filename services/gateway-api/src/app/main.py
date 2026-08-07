"""FastAPI application entry point for gateway-api.

Single responsibility: construct the FastAPI app and mount routers. Business
logic (auth, provisioning, routing) lives in routers/, repositories/,
dependencies/ -- not here. See README.md for this service's owns/does-not-own
boundary and implementation-plan.md section 3 for the repo layout this module
follows. Mirrors validation-service's app.main precedent.
"""

from __future__ import annotations

from fastapi import FastAPI

from app.routers import runs

app = FastAPI(
    title="gateway-api",
    description="The only internet-facing service (see README.md).",
    version="0.1.0",
)

app.include_router(runs.router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}
