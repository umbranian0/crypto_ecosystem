"""GW-008: outbound HTTP client provider for calls to internal services.

Single responsibility: give route handlers a `Depends()`-injectable
`httpx.Client` pointed at `VALIDATION_SERVICE_URL` (env var, default
`http://localhost:8000` -- no `infra/docker-compose.yml` dependency for local
dev, ticket Design section). Tests override this provider with a client built
on `httpx.MockTransport`/`httpx.ASGITransport` via `app.dependency_overrides`,
the same pattern GW-006/GW-007's tests use for repository fakes.

GW-009: `timeout=` is set from `GATEWAY_API_DOWNSTREAM_TIMEOUT_SECONDS` (env
var, default 30.0) so a slow/unreachable `validation-service` doesn't hang a
gateway request indefinitely -- `app.routers.runs` translates the resulting
`httpx.TimeoutException`/`httpx.ConnectError` into `504`/`502`.

GW-018: `get_reporting_service_client`/`ReportingServiceClientDep` follow the
exact same shape, pointed at `REPORTING_SERVICE_URL` (env var, default
`http://localhost:8002` -- matching `reporting-service`'s own Dockerfile
`EXPOSE 8002`) instead of collapsing both downstream services onto one client
with a runtime-branched base URL (ticket Design section: two named providers,
not one client that needs to know which service it's talking to per call).
"""

from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastapi import Depends

_VALIDATION_SERVICE_URL_ENV_VAR = "VALIDATION_SERVICE_URL"
_DEFAULT_VALIDATION_SERVICE_URL = "http://localhost:8000"

_REPORTING_SERVICE_URL_ENV_VAR = "REPORTING_SERVICE_URL"
_DEFAULT_REPORTING_SERVICE_URL = "http://localhost:8002"

_DOWNSTREAM_TIMEOUT_ENV_VAR = "GATEWAY_API_DOWNSTREAM_TIMEOUT_SECONDS"
_DEFAULT_DOWNSTREAM_TIMEOUT_SECONDS = 30.0


def get_validation_service_client() -> httpx.Client:
    base_url = os.environ.get(_VALIDATION_SERVICE_URL_ENV_VAR, _DEFAULT_VALIDATION_SERVICE_URL)
    timeout = float(
        os.environ.get(_DOWNSTREAM_TIMEOUT_ENV_VAR, _DEFAULT_DOWNSTREAM_TIMEOUT_SECONDS)
    )
    return httpx.Client(base_url=base_url, timeout=timeout)


def get_reporting_service_client() -> httpx.Client:
    base_url = os.environ.get(_REPORTING_SERVICE_URL_ENV_VAR, _DEFAULT_REPORTING_SERVICE_URL)
    timeout = float(
        os.environ.get(_DOWNSTREAM_TIMEOUT_ENV_VAR, _DEFAULT_DOWNSTREAM_TIMEOUT_SECONDS)
    )
    return httpx.Client(base_url=base_url, timeout=timeout)


ValidationServiceClientDep = Annotated[httpx.Client, Depends(get_validation_service_client)]
ReportingServiceClientDep = Annotated[httpx.Client, Depends(get_reporting_service_client)]
