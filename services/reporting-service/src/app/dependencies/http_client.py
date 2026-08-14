"""RS-004: outbound HTTP client provider for the call to
`validation-service` (this service's only downstream service call this
sprint).

Mirrors gateway-api's `app.dependencies.http_client` shape exactly (ticket
DRY check note) -- a `Depends()`-injectable `httpx.Client` pointed at
`VALIDATION_SERVICE_URL` (same env var name gateway-api already uses, scope
decision 5: this is the same kind of internal-hostname call). Tests override
this provider with a client built on `httpx.MockTransport`, the same pattern
gateway-api's GW-008/GW-009 tests use.

`timeout=` is set from `REPORTING_SERVICE_DOWNSTREAM_TIMEOUT_SECONDS` (env
var, default 30.0, mirrors gateway-api's own
`GATEWAY_API_DOWNSTREAM_TIMEOUT_SECONDS` naming convention) so a slow/
unreachable `validation-service` doesn't hang a report-generation request
indefinitely -- `app.generation` translates the resulting
`httpx.TimeoutException`/`httpx.ConnectError` into typed exceptions the
router maps to `504`/`502`.
"""

from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastapi import Depends

_VALIDATION_SERVICE_URL_ENV_VAR = "VALIDATION_SERVICE_URL"
_DEFAULT_VALIDATION_SERVICE_URL = "http://localhost:8000"

_DOWNSTREAM_TIMEOUT_ENV_VAR = "REPORTING_SERVICE_DOWNSTREAM_TIMEOUT_SECONDS"
_DEFAULT_DOWNSTREAM_TIMEOUT_SECONDS = 30.0


def get_validation_service_client() -> httpx.Client:
    base_url = os.environ.get(_VALIDATION_SERVICE_URL_ENV_VAR, _DEFAULT_VALIDATION_SERVICE_URL)
    timeout = float(
        os.environ.get(_DOWNSTREAM_TIMEOUT_ENV_VAR, _DEFAULT_DOWNSTREAM_TIMEOUT_SECONDS)
    )
    return httpx.Client(base_url=base_url, timeout=timeout)


ValidationServiceClientDep = Annotated[httpx.Client, Depends(get_validation_service_client)]
