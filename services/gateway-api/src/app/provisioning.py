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
"""

from __future__ import annotations

import hashlib
import logging
import secrets

from app.repositories.interfaces import ApiKeyRepository, TenantRecord, TenantRepository

logger = logging.getLogger(__name__)


def provision(
    name: str,
    tenant_repo: TenantRepository,
    api_key_repo: ApiKeyRepository,
) -> tuple[TenantRecord, str]:
    """Creates a tenant and its first API key, returning the tenant record
    and the raw (unhashed) key. Only `api_key_repo.create_key` is given the
    hash; the raw key lives solely in this function's return value and the
    caller's handling of it from there.
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

    return tenant, raw_key
