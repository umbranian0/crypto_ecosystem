"""DASH-003: session -> outbound gateway-api header DI seam.

Single responsibility: every future authenticated dashboard-web route
(DASH-004/006/007) depends on `DownstreamHeadersDep`/`GatewayApiUrlDep`
instead of hand-rolling its own cookie read, `SessionStore.get` call, or
`Authorization` header dict -- this module is the *only* place either of
those two things happens (Review acceptance criteria, checked again at each
future consumer's own review).

Pattern: Dependency Injection (implementation-plan.md section 7), the same
seam `gateway-api`'s `get_authenticated_tenant`
(`services/gateway-api/src/app/dependencies/auth.py`) instantiates for its
own service -- this is `dashboard-web`'s equivalent, not a new pattern.

Deliberate deviation from `get_authenticated_tenant`'s precedent: that
dependency raises `HTTPException(401)` because it backs a JSON API. This one
raises `HTTPException(303, headers={"Location": "/login"})` instead, because
it backs HTML-rendering routes -- a bare 401 JSON body would be the wrong
response for a browser navigation. FastAPI resolves `Depends()` parameters
before executing a route handler's own body, so raising here means an
unauthenticated request never reaches any route logic that declares
`DownstreamHeadersDep` as a parameter.
"""

from __future__ import annotations

import os
from typing import Annotated

from fastapi import Depends, HTTPException, Request

from app.dependencies.session import SessionStoreDep

_SESSION_COOKIE_NAME = "session_id"
_GATEWAY_API_URL_ENV_VAR = "GATEWAY_API_URL"
_DEFAULT_GATEWAY_API_URL = "http://localhost:8000"


def get_session_headers(request: Request, session_store: SessionStoreDep) -> dict[str, str]:
    """Resolves the `session_id` cookie to an `Authorization` header via
    `SessionStore.get` (DASH-002, imported not reimplemented). Missing
    cookie or an id unknown to the store (expired/never
    existed/already logged out) redirects to `/login` before any route body
    that depends on this executes.
    """
    session_id = request.cookies.get(_SESSION_COOKIE_NAME)
    api_key = session_store.get(session_id) if session_id is not None else None

    if api_key is None:
        raise HTTPException(status_code=303, headers={"Location": "/login"})

    return {"Authorization": f"Bearer {api_key}"}


def get_gateway_api_url() -> str:
    """Reads the same `GATEWAY_API_URL` env var/default DASH-002's
    `app.dependencies.http_client.get_gateway_api_client` already uses --
    reconciled to one canonical name rather than a second, differently-named
    one (ticket Design section).
    """
    return os.environ.get(_GATEWAY_API_URL_ENV_VAR, _DEFAULT_GATEWAY_API_URL)


DownstreamHeadersDep = Annotated[dict[str, str], Depends(get_session_headers)]
GatewayApiUrlDep = Annotated[str, Depends(get_gateway_api_url)]
