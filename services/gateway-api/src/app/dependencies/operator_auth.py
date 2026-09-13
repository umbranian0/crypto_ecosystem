"""GW-021: operator-token authentication dependency.

Single responsibility: resolve the callers presented X-Operator-Token
header to is-the-operator (boolean gate, no tenant context involved), or
raise HTTPException(401).

This is a narrow, deliberate stopgap -- one shared OPERATOR_TOKEN secret
for the whole operator surface, not a multi-admin user table (that remains
SETUP-010/SETUP-011 own, out-of-scope backlog).

Structurally separate from get_authenticated_tenant on purpose: no shared
function, no shared header name, no shared grant path. A tenants own API
key is checked against api_keys.key_hash via ApiKeyRepository;
OPERATOR_TOKEN's hash comparison remains the sole path to a 200 here.

SETUP-010: on the failure branch only -- after the presented value's hash
has already failed to match OPERATOR_TOKEN's hash -- this dependency now
does consult ApiKeyRepository.get_by_hash, purely to classify the
rejection. If the presented value resolves to a real, non-revoked tenant
ApiKeyRecord, that is a real credential of the wrong kind for this gate,
so HTTPException(403) is raised instead of 401. A revoked tenant key, or
a value that resolves to nothing at all, still raises 401, unchanged from
GW-021. The repository is never consulted on any path that can lead to a
200, so there is still no code path by which a tenant's own key could
ever satisfy this dependency.

Header sourcing follows the same ARCH-008 convention auth.py established:
Security() + fastapi.security.APIKeyHeader (never bare Header()), so
X-Operator-Token is registered as its own OpenAPI securityScheme.

Hashing/comparison: reuses the same hashlib.sha256(...).hexdigest()
hash-to-hash comparison discipline get_authenticated_tenant already
established (GW-006) -- never a raw-value == on the presented token, and
the presented token is never logged.

OPERATOR_TOKEN is read from the environment at dependency-call time (via
os.environ.get, not a module-level constant captured at import) so a
token rotated in the running environment takes effect on the very next
request, with no restart-to-pick-up-env-change gap.
"""

from __future__ import annotations

import hashlib
import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

from app.dependencies.repositories import ApiKeyRepositoryDep

_OPERATOR_TOKEN_ENV_VAR = "OPERATOR_TOKEN"

_UNAUTHORIZED = HTTPException(status_code=401, detail="missing or invalid operator token")
_FORBIDDEN = HTTPException(status_code=403, detail="valid credential, wrong credential type for this gate")

_operator_token_scheme = APIKeyHeader(
    name="X-Operator-Token", scheme_name="XOperatorToken", auto_error=False
)


def get_authenticated_operator(
    api_key_repo: ApiKeyRepositoryDep,
    x_operator_token: str | None = Security(_operator_token_scheme),
) -> None:
    """FastAPI Depends() resolver gating operator-only routes. Raises
    HTTPException(401) on a missing token, an unset/empty OPERATOR_TOKEN
    environment value, or a hash mismatch against an unknown/revoked value
    -- before any downstream/routing code runs. Raises HTTPException(403)
    when a hash mismatch's presented value turns out to resolve to a real,
    non-revoked tenant ApiKeyRecord (SETUP-010) -- a real credential, just
    the wrong kind for this gate. Returns None on success: there is no
    operator identity to carry forward, only a pass/fail gate (unlike
    get_authenticated_tenant, which resolves a TenantContext).
    """
    if not x_operator_token:
        raise _UNAUTHORIZED

    expected_token = os.environ.get(_OPERATOR_TOKEN_ENV_VAR)
    if not expected_token:
        raise _UNAUTHORIZED

    presented_hash = hashlib.sha256(x_operator_token.encode()).hexdigest()
    expected_hash = hashlib.sha256(expected_token.encode()).hexdigest()

    if presented_hash != expected_hash:
        # SETUP-010: the repository is consulted only here, on the
        # already-failed branch, purely to classify the 4xx -- it can never
        # contribute to a 200, since the function has already committed to
        # rejecting by the time this line runs.
        record = api_key_repo.get_by_hash(presented_hash)
        if record is not None and record.revoked_at is None:
            raise _FORBIDDEN
        raise _UNAUTHORIZED
