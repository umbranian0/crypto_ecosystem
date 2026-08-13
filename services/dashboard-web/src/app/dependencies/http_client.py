"""DASH-002: outbound HTTP client provider for calls to gateway-api.

Single responsibility: give route handlers a `Depends()`-injectable
`httpx.Client` pointed at `GATEWAY_API_URL` (env var, default
`http://localhost:8000` -- README.md's "Local setup" note). Tests override
this provider with a client built on `httpx.MockTransport` via
`app.dependency_overrides`, the same pattern gateway-api's own
`app.dependencies.http_client` uses for its `validation-service` client
(same module shape, one hop down the chain).
"""

from __future__ import annotations

import os
from typing import Annotated

import httpx
from fastapi import Depends

_GATEWAY_API_URL_ENV_VAR = "GATEWAY_API_URL"
_DEFAULT_GATEWAY_API_URL = "http://localhost:8000"


def get_gateway_api_client() -> httpx.Client:
    base_url = os.environ.get(_GATEWAY_API_URL_ENV_VAR, _DEFAULT_GATEWAY_API_URL)
    return httpx.Client(base_url=base_url, timeout=30.0)


GatewayApiClientDep = Annotated[httpx.Client, Depends(get_gateway_api_client)]
