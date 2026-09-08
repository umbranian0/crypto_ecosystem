"""FastAPI application entry point for dashboard-web (DASH-001).

Single responsibility: construct the FastAPI app, mount the Jinja2 template
environment, and mount routers as later tickets add them (DASH-002's
auth/session router, DASH-004/006's runs router, DASH-008's health check).
No business logic here -- mirrors gateway-api's/validation-service's own
app.main precedent (implementation-plan.md section 3).

This service owns no data access of its own (see README.md's "Does not own"
section): every route this app will grow calls out to gateway-api over HTTP
via `httpx`, never another service's code or database schema directly.
"""

from __future__ import annotations

from pathlib import Path

import httpx
from fastapi import FastAPI
from fastapi.responses import JSONResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from fastapi.templating import Jinja2Templates

from app.dependencies.downstream import get_gateway_api_url
from app.dependencies.http_client import GatewayApiClientDep

TEMPLATES_DIR = Path(__file__).parent / "templates"
STATIC_DIR = Path(__file__).parent / "static"

app = FastAPI(
    title="dashboard-web",
    description=(
        "Server-rendered validation/audit UI for a tenant to log in, submit a "
        "run, and view its results via gateway-api. Not a price-prediction or "
        "trading-signal surface -- see ../../CLAUDE.md's positioning constraint."
    ),
    version="0.1.0",
)

templates = Jinja2Templates(directory=str(TEMPLATES_DIR))

# Presentation-layer-only static assets (CSS); no route logic here, so this is
# mounted directly rather than via a router module.
app.mount("/static", StaticFiles(directory=str(STATIC_DIR)), name="static")

# Imported after `templates` is defined: `app.routers.auth` (DASH-002),
# `app.routers.runs` (DASH-004), `app.routers.operator` (DASH-113), and
# `app.routers.settings` (DASH-112) all read `templates` back from this
# module, so `templates` must already exist in this module's namespace
# before any of these imports run. `operator`/`settings` are imported after
# `runs` since both import `_call_downstream`/`_render_error_for_status`
# from that module (DASH-113's own DRY-reuse note, extended by DASH-112).
# `setup` (SETUP-003) is imported last for the same reason -- it also
# imports `_call_downstream`/`_render_error_for_status` from `runs`.
from app.routers import auth, operator, runs, settings, setup  # noqa: E402

app.include_router(auth.router)
app.include_router(runs.router)
app.include_router(operator.router)
app.include_router(settings.router)
app.include_router(setup.router)


@app.get("/")
def root(client: GatewayApiClientDep) -> RedirectResponse:
    """SETUP-003: root now checks gateway-api's `GET /setup/status` first --
    `initialized: false` (fresh install) redirects to `/setup` instead of
    `/runs`/`/login`; `initialized: true` (unchanged behavior) redirects to
    `/runs`, which itself redirects to `/login` via the existing session
    dependency if no tenant session cookie is present. A transport failure
    talking to gateway-api degrades to the existing `/runs` path rather than
    blocking the root route entirely -- gateway-api being briefly unreachable
    should not itself prevent an already-logged-in tenant from reaching
    `/runs` (which has its own, independent failure handling once reached).

    Takes `GatewayApiClientDep` directly (the same injectable/mockable
    provider `app.routers.setup`'s own routes use) rather than calling
    `setup.is_initialized_via_default_client()`, so this route's own tests
    can override the client the same way every other route's tests already
    do (`app.dependency_overrides[get_gateway_api_client]`).
    """
    initialized = setup.is_initialized(client)
    if initialized is False:
        return RedirectResponse(url="/setup")
    return RedirectResponse(url="/runs")


@app.get("/health", response_model=None)
def health() -> dict[str, str] | JSONResponse:
    """DASH-008: deliberately unauthenticated -- no `DownstreamHeadersDep`, so
    an operator/orchestrator health-checking this service needs no tenant
    session. Reuses `get_gateway_api_url` (DASH-003) rather than reading the
    `GATEWAY_API_URL` env var a second, differently-named way.

    Real connectivity check against gateway-api's own `/health`, matching its
    and validation-service's OPS-005-01/02 response-body shape: success
    `200 {"status": "ok"}`; any transport failure or non-200 from gateway-api
    is collapsed into a fixed generic `503` body -- no hostname/exception
    text leaked into the response.
    """
    try:
        response = httpx.get(
            f"{get_gateway_api_url()}/health",
            timeout=5.0,
        )
        if response.status_code == 200:
            return {"status": "ok"}
    except Exception:
        pass

    return JSONResponse(
        status_code=503,
        content={"status": "unhealthy", "detail": "gateway-api unreachable"},
    )
