"""GW-005/SETUP-002: the single tenant-provisioning function, shared by
`scripts/provision_tenant.py` (CLI, operator/test-fixture tool) and
`app.routers.setup`'s `POST /setup/initialize` (SETUP-002, bootstrap-only
network path). One function, two callers -- never two implementations
(implementation-plan.md section 9, DRY).

Moved here (out of `scripts/provision_tenant.py`, where it originally lived)
because `scripts/` is not installed as part of this service's package (see
`pyproject.toml`'s `[tool.hatch.build.targets.wheel]` -- only `src/app` is
packaged) and is not reliably importable from inside the running FastAPI app
process. `scripts/provision_tenant.py` keeps its CLI entry point and now
imports `provision` from here as a thin wrapper -- its own documented
behavior (`--name` argument, printing the tenant id and the raw key exactly
once to stdout) is unchanged.

GW-030: after the tenant + API key are created, `provision()` also triggers
`INGEST-030`'s `POST /internal/seed-platform-history` on `ingestion-service`
for the new tenant, synchronously, degraded-not-blocking (ticket Design
section). Reuses `app.dependencies.http_client.get_ingestion_service_client`
(GW-021, already wired for the proxy routes in `app.routers.operator`) rather
than constructing a second httpx client provider -- `provision()` is a plain
function, not a route handler, so it cannot use FastAPI's `Depends()`
directly, and instead takes an optional `ingestion_client` parameter,
defaulting to a freshly built client from that same provider (mirrors the
existing pattern of `provision()` accepting `tenant_repo`/`api_key_repo` as
injectable parameters rather than reaching for a global). Any transport
exception or non-2xx response from the seed call is caught, logged as a
structured `tenant_seed_degraded` warning (same `extra={...}` convention as
this file's own `api_key_issued` log line), and never re-raised -- tenant
creation itself always succeeds regardless of the seed call's outcome. The
downstream endpoint (`INGEST-030`) is already idempotent, so a retried seed
call for the same tenant is safe; no additional idempotency logic is added
here.
"""

from __future__ import annotations

import hashlib
import logging
import os
import secrets

import httpx

from app.dependencies.http_client import get_ingestion_service_client
from app.repositories.interfaces import ApiKeyRepository, TenantRecord, TenantRepository

logger = logging.getLogger(__name__)

_INGESTION_INTERNAL_TOKEN_ENV_VAR = "INGESTION_INTERNAL_TOKEN"


def provision(
    name: str,
    tenant_repo: TenantRepository,
    api_key_repo: ApiKeyRepository,
    ingestion_client: httpx.Client | None = None,
) -> tuple[TenantRecord, str]:
    """Creates a tenant and its first API key, returning the tenant record
    and the raw (unhashed) key. Only `api_key_repo.create_key` is given the
    hash; the raw key lives solely in this function's return value and the
    caller's handling of it from there.

    Also triggers (GW-030) a synchronous, degraded-not-blocking call to
    `ingestion-service`'s `POST /internal/seed-platform-history` for the new
    tenant -- a downstream failure there never affects this function's
    return value or raises out of it.
    """
    tenant = tenant_repo.create_tenant(name)

    raw_key = secrets.token_urlsafe(32)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    api_key_repo.create_key(tenant.id, key_hash)

    logger.info(
        "api key issued",
        extra={
            "event_type": "api_key_issued",
            "outcome": "success",
            "tenant_id": tenant.id,
        },
    )

    _seed_platform_history(tenant.id, ingestion_client)

    return tenant, raw_key


def _seed_platform_history(tenant_id: str, ingestion_client: httpx.Client | None) -> None:
    client = ingestion_client if ingestion_client is not None else get_ingestion_service_client()
    try:
        response = client.post(
            "/internal/seed-platform-history",
            json={"tenant_id": tenant_id},
            headers={"X-Internal-Token": os.environ.get(_INGESTION_INTERNAL_TOKEN_ENV_VAR, "")},
        )
        response.raise_for_status()
    except httpx.HTTPError:
        logger.warning(
            "tenant platform-history seed failed",
            extra={
                "event_type": "tenant_seed_degraded",
                "outcome": "degraded",
                "tenant_id": tenant_id,
            },
        )
