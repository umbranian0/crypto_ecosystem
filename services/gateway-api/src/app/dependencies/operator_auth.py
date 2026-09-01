"""GW-021: operator-token authentication dependency.

Single responsibility: resolve the callers presented X-Operator-Token
header to is-the-operator (boolean gate, no tenant context involved), or
raise HTTPException(401).

This is a narrow, deliberate stopgap -- one shared OPERATOR_TOKEN secret
for the whole operator surface, not a multi-admin user table (that remains
SETUP-010/SETUP-011 own, out-of-scope backlog).

Structurally separate from get_authenticated_tenant on purpose: no shared
function, no shared header name, no shared repository lookup. A tenants
own API key is checked against api_keys.key_hash via ApiKeyRepository;
this dependency never touches that repository at all and compares only
against the single OPERATOR_TOKEN environment value, so there is no code
path by which one credential could ever satisfy the others dependency.

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

_OPERATOR_TOKEN_ENV_VAR = "OPERATOR_TOKEN"

_UNAUTHORIZED = HTTPException(status_code=401, detail="missing or invalid operator token")

_operator_token_scheme = APIKeyHeader(name="X-Operator-Token", auto_error=False)


def get_authenticated_operator(
    x_operator_token: str | None = Security(_operator_token_scheme),
) -> None:
    """FastAPI Depends() resolver gating operator-only routes. Raises
    HTTPException(401) on a missing token, an unset/empty OPERATOR_TOKEN
    environment value, or a hash mismatch -- before any downstream/routing
    code runs. Returns None on success: there is no operator identity to
    carry forward, only a pass/fail gate (unlike get_authenticated_tenant,
    which resolves a TenantContext).
    """
    if not x_operator_token:
        raise _UNAUTHORIZED

    expected_token = os.environ.get(_OPERATOR_TOKEN_ENV_VAR)
    if not expected_token:
        raise _UNAUTHORIZED

    presented_hash = hashlib.sha256(x_operator_token.encode()).hexdigest()
    expected_hash = hashlib.sha256(expected_token.encode()).hexdigest()

    if presented_hash != expected_hash:
        raise _UNAUTHORIZED
