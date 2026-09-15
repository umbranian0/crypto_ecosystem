"""INGEST-030: `POST /internal/seed-platform-history` -- service-authenticated,
single-tenant platform-history seed endpoint.

Single responsibility: adapt an internal, `gateway-api`-originated HTTP
request into a direct call of `app.seed_platform_history.
seed_tenant_platform_history` (`INGEST-010`) for the one `tenant_id` named
in the request body -- no second, divergent CSV-parsing/DB-writing
implementation (DRY check, ticket Design section). Deliberately not added
to `connectors.py`/`datasets.py`: this is a different concern
(service-to-service, not tenant-authenticated).

Auth: `get_authenticated_internal_caller` (`app.dependencies.internal_auth`),
gating on `X-Internal-Token` against `INGESTION_INTERNAL_TOKEN` -- not
`X-Tenant-Id`/tenant API-key auth, since this endpoint is called immediately
after tenant creation, before any tenant API key exists.

Error handling mirrors `main.py`'s `GET /health` failure-response
discipline: any exception from the write path is caught and returned as a
generic `503` body, never the raw exception text (which could carry a
Postgres connection string/credential).
"""

from __future__ import annotations

from fastapi import APIRouter, Depends
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from app.dependencies.internal_auth import get_authenticated_internal_caller
from app.dependencies.repositories import ConnectorRecordRepositoryDep
from app.seed_platform_history import seed_tenant_platform_history

router = APIRouter(dependencies=[Depends(get_authenticated_internal_caller)])


class SeedPlatformHistoryRequest(BaseModel):
    tenant_id: str


class SeedPlatformHistoryResponse(BaseModel):
    row_counts: dict[str, int]


@router.post(
    "/internal/seed-platform-history",
    response_model=None,
)
def seed_platform_history(
    request: SeedPlatformHistoryRequest,
    connector_repository: ConnectorRecordRepositoryDep,
) -> SeedPlatformHistoryResponse | JSONResponse:
    try:
        row_counts = seed_tenant_platform_history(request.tenant_id, connector_repository)
    except Exception:
        # No raw exception text/connection string/credential in the response
        # body -- a fixed, generic detail string only, matching GET /health's
        # own failure-response convention.
        return JSONResponse(
            status_code=503,
            content={"status": "error", "detail": "platform-history seed failed"},
        )
    return SeedPlatformHistoryResponse(row_counts=row_counts)
