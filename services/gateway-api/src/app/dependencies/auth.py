"""GW-006: API-key authentication dependency.

Single responsibility: resolve the caller's presented API key (`Authorization:
Bearer <key>` checked first, `X-Api-Key: <key>` as fallback) to a
`naive_first_common.TenantContext`, or raise `HTTPException(401)`.

Pattern: FastAPI `Depends()`, same mechanism as `naive_first_common`'s own
`get_tenant_context` precedent (`libs/common/src/naive_first_common/
tenant_context.py`) -- but this is `gateway-api`'s own resolver, not a call
into that module. `naive_first_common` knows nothing about `api_keys.key_hash`
and must not be taught to know about it (backlog decision 3's boundary).

Both headers are read via `fastapi.security.APIKeyHeader` (`Security()`,
not bare `Header()`) purely so FastAPI registers them as OpenAPI
`securitySchemes` -- this is what makes Swagger UI show a single top-level
"Authorize" button where a key is entered once and then attached
automatically to every subsequent "Try it out" call, instead of requiring
the two header fields to be re-typed per endpoint. `APIKeyHeader` still just
returns the raw header string (or `None`) with no parsing/validation of its
own -- all format-checking stays in `_extract_raw_key` below, unchanged.

Result type (design decision, GW-006 ticket Design section): reuses
`naive_first_common.TenantContext` itself rather than defining a second,
parallel value type -- `gateway-api` already depends on `naive_first_common`
(GW-001) and the shape (a validated `tenant_id`) is identical, so a second
type here would be exactly the duplicate-shape DRY violation
implementation-plan.md section 9 warns against. GW-007 forwards this same
object.

Hashing (sprint-05.md's binding, non-negotiable choice, not re-litigated
here): `hashlib.sha256(...).hexdigest()` -- never bcrypt/argon2/scrypt.
Comparison is exclusively hash-to-hash, via `ApiKeyRepository.get_by_hash`'s
SQL-level exact match (GW-004) -- no raw key is ever compared against a
stored value, because no raw key is ever stored (GW-002/GW-004).

The presented raw key is never logged, printed, or included in any exception
message anywhere in this module -- only the resulting `tenant_id`
(post-authentication) may appear in any log/error path.
"""

from __future__ import annotations

import hashlib

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader
from naive_first_common.tenant_context import TenantContext

from app.dependencies.repositories import ApiKeyRepositoryDep

_UNAUTHORIZED = HTTPException(status_code=401, detail="missing or invalid API key")

_authorization_scheme = APIKeyHeader(name="Authorization", auto_error=False)
_x_api_key_scheme = APIKeyHeader(name="X-Api-Key", auto_error=False)


def _extract_raw_key(
    authorization: str | None,
    x_api_key: str | None,
) -> str:
    """Raw-key extraction seam: `Authorization: Bearer <key>` checked first,
    `X-Api-Key: <key>` as fallback (ticket Design section). Raises 401 on
    anything not cleanly one of those two well-formed shapes.
    """
    if authorization is not None:
        scheme, _, key = authorization.partition(" ")
        if scheme != "Bearer" or not key:
            raise _UNAUTHORIZED
        return key

    if x_api_key is not None:
        if not x_api_key:
            raise _UNAUTHORIZED
        return x_api_key

    raise _UNAUTHORIZED


def get_authenticated_tenant(
    api_key_repo: ApiKeyRepositoryDep,
    authorization: str | None = Security(_authorization_scheme),
    x_api_key: str | None = Security(_x_api_key_scheme),
) -> TenantContext:
    """FastAPI `Depends()` resolver for the current request's authenticated
    tenant. Missing/malformed header, unknown key, or a revoked key all raise
    `HTTPException(401)` before any downstream/routing code runs.
    """
    raw_key = _extract_raw_key(authorization, x_api_key)
    key_hash = hashlib.sha256(raw_key.encode()).hexdigest()

    record = api_key_repo.get_by_hash(key_hash)
    if record is None or record.revoked_at is not None:
        raise _UNAUTHORIZED

    return TenantContext(tenant_id=record.tenant_id)
