"""DASH-002: login screen exchanging a tenant's raw gateway-api API key for a
server-side session.

Pattern: Dependency Injection only (implementation-plan.md section 7) -- see
`app.dependencies.session.SessionStore` and `app.dependencies.http_client`
for the two injected collaborators.

Security-critical invariants (ticket Design section, binding):
- The raw submitted API key is never rendered back into any HTML/JS response
  body (the `login.html` error-redisplay path never echoes the submitted
  value), never logged/printed, and never placed in a URL/query
  string/redirect `Location` header. It is sent to gateway-api exactly once,
  as `Authorization: Bearer <key>` (gateway-api's documented primary header
  shape, GW-006) -- never the `X-Api-Key` fallback.
- The session cookie holds only the opaque `session_id`
  (`secrets.token_urlsafe(32)`, minted by `SessionStore.create`) -- the raw
  key itself never leaves `SessionStore`'s process-local dict. This is
  stronger than a signed cookie (e.g. Starlette's `SessionMiddleware`, whose
  contents are base64-readable without the signing secret) -- do not swap
  this for `SessionMiddleware` or any cookie-encodes-the-payload approach.
- `secure=True` on the cookie is gated behind `DASHBOARD_COOKIE_SECURE` (env
  var, default `"false"` for this sprint's plain-HTTP local/Compose PoC,
  disclosed known gap in README.md, same spirit as gateway-api's own GW-007
  forwarding-mechanism caveat). `httponly=True` is set unconditionally.

Lazy validation (ticket Design section): gateway-api has no dedicated
"verify this key" endpoint and no other authenticated route exists yet at
this point in the ticket sequence, so `POST /login` calls gateway-api's
`GET /runs/{a random uuid4}` -- an authenticated endpoint (GW-006) that
returns `401` for a bad/missing key vs `404` for a well-formed-but-unknown
run for a *valid* key. Only `401` means "invalid key"; anything else
(including `404`) means the key round-tripped through gateway-api's auth
layer successfully. A transport-level failure (connection refused/timeout)
redisplays `/login` with a generic "gateway-api unreachable" error -- it is
not treated as an invalid key.

DASH-003 formalizes 401-handling for every *future* authenticated route via
its own shared dependency; this ticket's AC3 ("a 401 from any downstream call
redirects to /login and clears the session") is proven today only by this
handler's own lazy-validation call, since no other authenticated route
exists yet.

DASH-007: `POST /logout`, added to this same router module (same
auth-lifecycle file, not a new one, per this ticket's own Design section).
Depends on `DownstreamHeadersDep` (DASH-003, imported not reimplemented) so
an already-invalid/missing session is redirected to `/login` by that existing
dependency before this handler's own body ever runs -- logging out an
already-logged-out session is a no-op that ends at `/login` either way, so no
second validity check is written here. The handler itself reads the raw
`session_id` cookie (not the resolved `Authorization` header -- `SessionStore
.delete` needs the session id, not the API key), calls `SessionStore.delete`
(DASH-002, imported not reimplemented), clears the cookie via
`Response.delete_cookie`, and redirects (303) to `/login`.
"""

from __future__ import annotations

import os
import uuid

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.dependencies.downstream import DownstreamHeadersDep
from app.dependencies.http_client import GatewayApiClientDep
from app.dependencies.session import SessionStoreDep
from app.main import templates

router = APIRouter()

_COOKIE_SECURE_ENV_VAR = "DASHBOARD_COOKIE_SECURE"
_SESSION_COOKIE_NAME = "session_id"
_UNREACHABLE_ERROR = "gateway-api is unreachable. Please try again shortly."
_INVALID_KEY_ERROR = "Invalid API key."
_EMPTY_KEY_ERROR = "API key is required."


def _cookie_secure() -> bool:
    return os.environ.get(_COOKIE_SECURE_ENV_VAR, "false").strip().lower() == "true"


@router.get("/login")
def login_form(request: Request):
    return templates.TemplateResponse(request, "login.html", {})


@router.post("/login")
def login_submit(
    request: Request,
    client: GatewayApiClientDep,
    session_store: SessionStoreDep,
    api_key: str = Form(...),
):
    if not api_key.strip():
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": _EMPTY_KEY_ERROR},
            status_code=422,
        )

    probe_run_id = str(uuid.uuid4())
    try:
        response = client.get(
            f"/runs/{probe_run_id}",
            headers={"Authorization": f"Bearer {api_key}"},
        )
    except (httpx.ConnectError, httpx.TimeoutException):
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": _UNREACHABLE_ERROR},
            status_code=502,
        )

    if response.status_code == 401:
        return templates.TemplateResponse(
            request,
            "login.html",
            {"error": _INVALID_KEY_ERROR},
            status_code=401,
        )

    session_id = session_store.create(api_key)
    redirect = RedirectResponse(url="/runs/new", status_code=303)
    redirect.set_cookie(
        key=_SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=_cookie_secure(),
    )
    return redirect


@router.post("/logout")
def logout(
    request: Request,
    headers: DownstreamHeadersDep,
    session_store: SessionStoreDep,
):
    """`headers` is unused beyond enforcing DASH-003's session-validity check
    (an already-invalid/missing session redirects to `/login` before this
    body runs, per the ticket's Design section -- no second check here).
    """
    session_id = request.cookies.get(_SESSION_COOKIE_NAME)
    if session_id is not None:
        session_store.delete(session_id)

    redirect = RedirectResponse(url="/login", status_code=303)
    redirect.delete_cookie(_SESSION_COOKIE_NAME)
    return redirect
