"""SETUP-001: `GET /setup/status` -- the one deliberate, narrow
unauthenticated endpoint this service carries.

Per the ticket's Analysis section: `dashboard-web`'s setup flow needs an
unauthenticated way to ask "does any tenant exist yet" -- by definition no
credential can exist to gate that question on a genuinely fresh install (the
same chicken-and-egg reasoning `provision_tenant.py`'s own docstring already
applies to itself). No `Depends(get_authenticated_tenant)`/
`get_authenticated_operator` (or any auth dependency at all) is attached to
this route -- that absence is the entire point of this ticket, not an
oversight.

`SetupStatusResponse` has exactly one field, `initialized: bool` --
deliberately no tenant name/count/id or any other identifying detail, since
this route is reachable by anyone with network access to this service.

Deliberately a new module (same precedent `system.py`/`operator.py` already
established for a disjoint-file new router), not added to any existing
router -- keeps this ticket's diff disjoint from `SETUP-010`'s parallel work
on `dependencies/operator_auth.py`.

SETUP-002: `POST /setup/initialize` lives in this same module -- the
sprint's own File-overlap note calls this out as one new router file, not
two. No auth dependency is attached to this route either; it is gated by
the `tenant_exists()` `409` check instead, run *before* `provision()` is
ever called, not via catching a database-level uniqueness violation as a
side effect. Calls the exact same `provision()` function
`scripts/provision_tenant.py` already uses (now living in
`app.provisioning`, imported directly here) -- no second tenant-creation
code path.
"""

from __future__ import annotations

from fastapi import APIRouter, HTTPException
from pydantic import BaseModel

from app.dependencies.repositories import ApiKeyRepositoryDep, TenantRepositoryDep
from app.provisioning import provision

router = APIRouter()


class SetupStatusResponse(BaseModel):
    """Exactly one field (ticket Implementation acceptance criteria) --
    no tenant name/count/id or any other side-channel detail.
    """

    initialized: bool


@router.get("/setup/status")
def get_setup_status(tenant_repository: TenantRepositoryDep) -> SetupStatusResponse:
    return SetupStatusResponse(initialized=tenant_repository.tenant_exists())


class SetupInitializeRequest(BaseModel):
    tenant_name: str


class SetupInitializeResponse(BaseModel):
    tenant_id: str
    tenant_name: str
    api_key: str


@router.post("/setup/initialize", status_code=201)
def post_setup_initialize(
    body: SetupInitializeRequest,
    tenant_repository: TenantRepositoryDep,
    api_key_repository: ApiKeyRepositoryDep,
) -> SetupInitializeResponse:
    # SETUP-002: the 409 guard runs before any write -- tenant_exists() is a
    # read, so a fresh install always reaches provision() below exactly
    # once; any subsequent call short-circuits here with zero writes.
    if tenant_repository.tenant_exists():
        raise HTTPException(status_code=409, detail="already initialized")

    tenant, raw_key = provision(body.tenant_name, tenant_repository, api_key_repository)

    return SetupInitializeResponse(tenant_id=tenant.id, tenant_name=tenant.name, api_key=raw_key)
