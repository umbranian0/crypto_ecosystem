"""INGEST-030: service-to-service authentication dependency for
`POST /internal/seed-platform-history`.

Copied with attribution from `services/gateway-api/src/app/dependencies/
operator_auth.py`'s `get_authenticated_operator` (GW-021) -- same
env-var-compare shape, same missing/unset-env-var-or-mismatched-token ->
401 behavior -- but a distinct secret (`INGESTION_INTERNAL_TOKEN`, not
`OPERATOR_TOKEN`) and a distinct header (`X-Internal-Token`, not
`X-Operator-Token`), since this gate authenticates gateway-api calling this
service on a tenant's behalf (immediately after tenant creation, before any
tenant API key exists), not an operator acting directly. Unlike
`operator_auth.py`, there is no `ApiKeyRepository` consultation on the
failure branch -- that 401-vs-403 reclassification is specific to
`operator_auth.py`'s own tenant-API-key-confusion scenario, which has no
equivalent here (this endpoint has no tenant-key acceptance path at all).

Disclosed limitation (mirrors `operator_auth.py`'s own docstring note): one
shared `INGESTION_INTERNAL_TOKEN` secret for the whole gateway-api ->
ingestion-service surface, no per-caller identity -- an accepted MVP
tradeoff for a single internal caller, not a silent gap.

`INGESTION_INTERNAL_TOKEN` is read from the environment at dependency-call
time (`os.environ.get`, not a module-level constant captured at import), so
a token rotated in the running environment takes effect on the very next
request -- same reasoning `operator_auth.py` documents for `OPERATOR_TOKEN`.
"""

from __future__ import annotations

import hashlib
import os

from fastapi import HTTPException, Security
from fastapi.security import APIKeyHeader

_INTERNAL_TOKEN_ENV_VAR = "INGESTION_INTERNAL_TOKEN"

_UNAUTHORIZED = HTTPException(status_code=401, detail="missing or invalid internal token")

_internal_token_scheme = APIKeyHeader(
    name="X-Internal-Token", scheme_name="XInternalToken", auto_error=False
)


def get_authenticated_internal_caller(
    x_internal_token: str | None = Security(_internal_token_scheme),
) -> None:
    """FastAPI `Depends()` resolver gating `POST /internal/seed-platform-history`.

    Raises `HTTPException(401)` on a missing header, an unset/empty
    `INGESTION_INTERNAL_TOKEN` environment value, or a hash mismatch -- all
    before any downstream repository/write code runs. Returns `None` on
    success: this is a pass/fail gate only, no caller identity to carry
    forward (mirrors `get_authenticated_operator`'s own return shape).
    """
    if not x_internal_token:
        raise _UNAUTHORIZED

    expected_token = os.environ.get(_INTERNAL_TOKEN_ENV_VAR)
    if not expected_token:
        raise _UNAUTHORIZED

    presented_hash = hashlib.sha256(x_internal_token.encode()).hexdigest()
    expected_hash = hashlib.sha256(expected_token.encode()).hexdigest()

    if presented_hash != expected_hash:
        raise _UNAUTHORIZED
