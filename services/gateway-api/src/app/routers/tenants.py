"""SETUP-011: operator-only tenant admin surface -- `GET /tenants`,
`POST /tenants`, `POST /tenants/{tenant_id}/api-keys/{key_id}/revoke`.

Deliberately a new module (same "one disjoint module per distinct concern"
precedent `setup.py`/`system.py`/`operator.py` already established).

Every route here is gated by `get_authenticated_operator` (SETUP-010) -- this
is an operator-only surface, replacing the
`docker compose exec ... provision_tenant.py`/`revoke_api_key.py` flow with a
network-reachable one `dashboard-web`'s Settings area (SETUP-012) can call.

**Never expose `key_hash`/a raw key**: `ApiKeySummary` below carries only
`id`/`created_at`/`revoked_at` -- no `key_hash` field exists anywhere in this
module's response models except `TenantCreateResponse.api_key`, which is the
raw key returned exactly once at creation time (the same one-time-reveal
contract `SETUP-002`'s `SetupInitializeResponse` already established).

**`POST /tenants` -- no second tenant-creation code path**: calls
`app.provisioning.provision()` directly, the exact function
`scripts/provision_tenant.py`/`SETUP-002`'s `POST /setup/initialize` already
share. Unlike `POST /setup/initialize`, there is no `409`-on-already-
initialized guard here -- this is a genuine ongoing multi-tenant creation
surface, gated by operator auth instead of the fresh-install check.

**Revoke granularity, resolved explicitly (ticket Analysis section)**: the
backlog's own wording says this endpoint "wraps `revoke_api_key.py`'s
`revoke()`", but that CLI function takes a *raw* API key as input -- the only
credential a CLI operator has on hand. An HTTP caller here has no raw key
after issuance (shown once, never persisted, GW-005's one-time-reveal
contract) -- it only has the key's `id` (metadata, from `GET /tenants`). The
correct shared call is therefore `ApiKeyRepository.revoke_key(tenant_id,
key_id)` directly -- the same repository method `revoke_api_key.py`'s own
`revoke()` calls internally after resolving a raw key to a `key_id`. This is
still "one shared function, not a duplicate revocation code path" -- the
shared function is `revoke_key` at the repository layer, one level lower than
`revoke_api_key.py`'s own CLI-specific `revoke()` wrapper, the correct level
to share at here since the two callers start from different inputs (raw key
vs. key id).

**404 scoping**: a `key_id` that does not belong to `tenant_id` (or does not
exist at all) is resolved via `list_api_keys(tenant_id)` and a match on
`key_id` -- no new lookup-by-id repository method needed. Both "key doesn't
exist" and "key exists but belongs to a different tenant" collapse to the
same generic 404, never a distinguishing detail in the response body (same
non-disclosure stance `validation-service`'s `GET /runs/{id}` already uses).

**Already-revoked is a no-op**: mirrors `revoke_api_key.py`'s own idempotency
guard -- `revoked_at` is checked before calling `revoke_key`, never
re-stamped with a new timestamp.

**Two front doors, one shared implementation**: `scripts/provision_tenant.py`/
`scripts/revoke_api_key.py` are unchanged by this ticket and still work --
they and this router are two separate callers of the same underlying
`provision()`/`revoke_key()` functions, not two competing implementations.
"""

from __future__ import annotations

from datetime import datetime

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel

from app.dependencies.operator_auth import get_authenticated_operator
from app.dependencies.repositories import ApiKeyRepositoryDep, TenantRepositoryDep
from app.provisioning import provision

router = APIRouter()


class ApiKeySummary(BaseModel):
    id: str
    created_at: datetime
    revoked_at: datetime | None


class TenantSummary(BaseModel):
    id: str
    name: str
    created_at: datetime
    api_keys: list[ApiKeySummary]


class TenantListResponse(BaseModel):
    items: list[TenantSummary]


@router.get("/tenants")
def list_tenants(
    tenant_repository: TenantRepositoryDep,
    api_key_repository: ApiKeyRepositoryDep,
    _operator: None = Depends(get_authenticated_operator),
) -> TenantListResponse:
    items = [
        TenantSummary(
            id=tenant.id,
            name=tenant.name,
            created_at=tenant.created_at,
            api_keys=[
                ApiKeySummary(id=key.id, created_at=key.created_at, revoked_at=key.revoked_at)
                for key in api_key_repository.list_api_keys(tenant.id)
            ],
        )
        for tenant in tenant_repository.list_tenants()
    ]
    return TenantListResponse(items=items)


class TenantCreateRequest(BaseModel):
    tenant_name: str


class TenantCreateResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    api_key: str


@router.post("/tenants", status_code=201)
def create_tenant(
    body: TenantCreateRequest,
    tenant_repository: TenantRepositoryDep,
    api_key_repository: ApiKeyRepositoryDep,
    _operator: None = Depends(get_authenticated_operator),
) -> TenantCreateResponse:
    tenant, raw_key = provision(body.tenant_name, tenant_repository, api_key_repository)
    return TenantCreateResponse(tenant_id=tenant.id, tenant_name=tenant.name, api_key=raw_key)


class RevokeApiKeyResponse(BaseModel):
    tenant_id: str
    key_id: str
    revoked_at: datetime


@router.post("/tenants/{tenant_id}/api-keys/{key_id}/revoke")
def revoke_api_key(
    tenant_id: str,
    key_id: str,
    api_key_repository: ApiKeyRepositoryDep,
    _operator: None = Depends(get_authenticated_operator),
) -> RevokeApiKeyResponse:
    keys = api_key_repository.list_api_keys(tenant_id)
    matched = next((key for key in keys if key.id == key_id), None)
    if matched is None:
        raise HTTPException(status_code=404, detail="not found")

    if matched.revoked_at is None:
        api_key_repository.revoke_key(tenant_id, key_id)
        keys = api_key_repository.list_api_keys(tenant_id)
        matched = next(key for key in keys if key.id == key_id)

    return RevokeApiKeyResponse(tenant_id=tenant_id, key_id=key_id, revoked_at=matched.revoked_at)
