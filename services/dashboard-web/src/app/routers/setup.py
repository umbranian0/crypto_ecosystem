"""SETUP-003: browser-based first-run setup wizard.

`GET /setup` renders a tenant-name form (or redirects straight to `/login`
if `gateway-api` already reports `initialized: true` -- no error surfaced,
no form re-render). `POST /setup` calls `gateway-api`'s `POST
/setup/initialize` (SETUP-002) and, on success, renders the raw API key
exactly once on a "copy this now -- it cannot be recovered" confirmation
page, mirroring `provision_tenant.py`'s/DASH-002's own one-time-reveal
discipline for a raw key: never logged, never placed in a URL/redirect
`Location` header, never echoed back into an error-redisplay path.

Deliberately not gated by `DownstreamHeadersDep` (DASH-003) or
`require_operator_session` (DASH-113) -- there is no session of either kind
possible yet on a fresh install, the same chicken-and-egg reasoning
`SETUP-001`/`SETUP-002` already applied gateway-api-side. Reuses
`GatewayApiClientDep` (DASH-002's `get_gateway_api_client` provider, the
same injectable/mockable `httpx.Client` every other route in this service
already uses) and `_call_downstream`/`_render_error_for_status` (runs.py,
DASH-004) for transport-failure handling -- no new HTTP-client or
error-translation mechanism invented for this router.

Positioning (CLAUDE.md, non-negotiable): this is the very first page a
brand-new operator sees. Copy describes only a "tenant" and an "API key for
validation runs" -- never anything implying trading/prediction capability.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.dependencies.http_client import GatewayApiClientDep
from app.main import templates
from app.routers.runs import _call_downstream, _render_error_for_status

router = APIRouter()


def is_initialized(client: httpx.Client) -> bool | None:
    """Calls `GET /setup/status` via the given client. Returns `None` on a
    transport-level failure (gateway-api unreachable) so callers can degrade
    gracefully rather than crash on a fresh, not-yet-up stack.
    """
    response, transport_status = _call_downstream(client.get, "/setup/status")
    if transport_status is not None or response.status_code != 200:
        return None
    return bool(response.json()["initialized"])


@router.get("/setup")
def setup_form(request: Request, client: GatewayApiClientDep):
    initialized = is_initialized(client)
    if initialized is None:
        return _render_error_for_status(request, 502)
    if initialized:
        # SETUP-003 AC: visiting /setup post-initialization redirects
        # straight to /login -- no error surfaced, no form re-render.
        return RedirectResponse(url="/login", status_code=303)

    return templates.TemplateResponse(request, "setup.html", {})


@router.post("/setup")
def setup_submit(
    request: Request,
    client: GatewayApiClientDep,
    tenant_name: str = Form(...),
):
    if not tenant_name.strip():
        return templates.TemplateResponse(
            request,
            "setup.html",
            {"error": "Tenant name is required."},
            status_code=422,
        )

    response, transport_status = _call_downstream(
        client.post, "/setup/initialize", json={"tenant_name": tenant_name}
    )
    if transport_status is not None:
        return _render_error_for_status(request, transport_status)

    if response.status_code == 409:
        # Reachable only via a direct POST (e.g. a stray double-submit), not
        # the normal UI flow (GET already redirects once initialized) --
        # degrade to the same not-an-error redirect rather than surfacing
        # gateway-api's 409 as a user-facing error.
        return RedirectResponse(url="/login", status_code=303)

    if response.status_code != 201:
        return _render_error_for_status(request, response.status_code)

    body = response.json()

    return templates.TemplateResponse(
        request,
        "setup_key_reveal.html",
        {"tenant_name": body["tenant_name"], "api_key": body["api_key"]},
        status_code=201,
    )
