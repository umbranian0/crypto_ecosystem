"""TenantContext: shared tenant-identity value object.

Passed across service boundaries (dependency-injected via FastAPI `Depends()`
in each service). See README.md "owns" boundary — no service-specific
fields belong here.
"""

from __future__ import annotations

from fastapi import Header, HTTPException
from pydantic import BaseModel, ConfigDict, ValidationError, field_validator


class TenantContext(BaseModel):
    """Identifies the tenant a request is scoped to.

    Frozen and validated at construction time so an invalid tenant_id can
    never exist as a live object, rather than being caught later by a
    caller-side check (see LC-002 Design: fail closed at construction).
    """

    model_config = ConfigDict(frozen=True)

    tenant_id: str

    @field_validator("tenant_id")
    @classmethod
    def _reject_blank_tenant_id(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("tenant_id must not be empty or whitespace-only")
        return stripped


def _extract_tenant_id(x_tenant_id: str | None) -> str | None:
    """Raw extraction seam. LC-009 will swap this body (or the header
    parameter it reads) for gateway-api-verified-auth-derived resolution;
    `get_tenant_context`'s signature and `Depends()` call sites don't change.
    """
    return x_tenant_id


def get_tenant_context(
    x_tenant_id: str | None = Header(default=None, alias="X-Tenant-Id"),
) -> TenantContext:
    """FastAPI `Depends()` resolver for the current request's `TenantContext`.

    Interim strategy (this ticket, LC-003): extracts `tenant_id` from the
    explicit `X-Tenant-Id` request header via the `_extract_tenant_id` seam.
    LC-009 will replace this with gateway-api-verified-auth-derived
    resolution; only `_extract_tenant_id` needs to change then.

    Missing, empty, or whitespace-only `tenant_id` raises 401 (not 400) so a
    route handler body never runs without a valid tenant context.
    """
    tenant_id = _extract_tenant_id(x_tenant_id)
    if tenant_id is None or not tenant_id.strip():
        raise HTTPException(status_code=401, detail="missing or empty tenant context")
    try:
        return TenantContext(tenant_id=tenant_id)
    except ValidationError as exc:
        raise HTTPException(status_code=401, detail="missing or empty tenant context") from exc
