"""DASH-113: minimal `/monitoring` page + operator-token session gate
(slice of `SETUP-012`/`020`).

Deliberately a new, disjoint router module (not added to `auth.py`/
`runs.py`) -- mirrors gateway-api's own precedent of a fresh module per
distinct concern (`system.py`'s own docstring cites the same reasoning for
GW-022), and keeps the operator surface's own auth mechanism (this file,
`app.dependencies.operator_session`) structurally separate from `auth.py`'s
tenant-session code (ticket Design/Review acceptance criteria).

`GET /operator-login` / `POST /operator-login`: an operator token form.
Unlike `POST /login` (DASH-002), there is no gateway-api endpoint that
validates a bare operator token today (ticket's own Analysis section) -- so
"success" here means only "a non-empty token was submitted"; the token is
stored, unvalidated, in `OperatorSessionStore` (`app.dependencies
.operator_session`, DASH-113) behind a cookie structurally distinct from the
tenant-session cookie (different name, different store instance -- see that
module's own docstring). A blank submission redisplays the form with an
error, the same "redisplay with error" convention `login.html`'s own empty-
key path (DASH-002) established.

`GET /monitoring`: calls gateway-api's `GET /system/health` (GW-022, no
auth required on gateway-api's own side per that ticket's explicit design
choice) and renders one row per service. Deliberately **not** gated behind
`require_operator_session` for this ticket's own scope (ticket Design
section: "your call, but keep it consistent with GW-022 requiring no
auth") -- viewing health status carries no tenant/operator-sensitive data.
Reuses `runs.py`'s `_call_downstream`/`_render_error_for_status` for the
transport-failure-reaching-gateway-api path (DRY check note: this is the
same "translate ConnectError/TimeoutException, render the shared
`error.html`" branch `runs.py`/`system.py` (gateway-api) already established
one hop up the chain -- extending `runs.py`'s import surface rather than a
second near-identical try/except in this file).

DASH-109: extends this same `GET /monitoring` route (not a second page, per
the ticket's own Review acceptance criteria) with a "last crawl status"
panel, one row per source the calling tenant has ingested. The fourth health
row (`ingestion-service`) required no change here at all -- `monitoring.html`
already renders every key `services` returns generically (one `{% for name,
status in services.items() %}` loop, no hardcoded three-service list), so
GW-022 already including a fourth key was sufficient by itself, confirmed by
this ticket rather than assumed.

**Auth design decision for the crawl-status panel** (`/monitoring` itself
stays unauthenticated, per the constraint above and `tests/test_monitoring.
py::test_monitoring_requires_no_session`, which must keep passing): the panel
needs a `TenantContext` to call `GET /ingestion/datasets`/`GET /ingestion/
connectors/{source}/status`, but gating the entire page behind
`DownstreamHeadersDep` (which redirects to `/login`) would break that
no-auth requirement for the page as a whole. Resolution: `OptionalDownstream
HeadersDep` (`app.dependencies.downstream`, DASH-109 addition, the same
cookie-read/`SessionStore.get` call `get_session_headers` already makes,
reused not duplicated) returns `None` instead of redirecting when no tenant
session exists. `/monitoring` itself remains reachable with zero session; the
panel shows a plain "log in to view your own ingestion status" message in
that case, and the real per-source table only once a tenant session cookie
is present -- an anonymous visitor sees the same aggregate health rows as
before, plus a login prompt for the one panel that is inherently
tenant-scoped data, rather than the whole page disappearing behind a
redirect.

DASH-110: adds two trigger actions to this same page (not a new page, per
the ticket's own Design section): a per-source "run this tenant's crawl now"
button in the crawl-status panel above, and a "generate a report" form. Both
are plain `POST` routes in this same router module -- structurally, every
action here is one outbound `httpx` call through `gateway-api`'s own public
HTTP contract, never a call into any container runtime's control surface or
a locally spawned OS-level process (the ticket's own structurally-enforced
boundary, decision #6, proven by this service's own zero-hits grep proof);
every trigger is a normal authenticated HTTP call through `gateway-api`'s
already-existing proxies (`GW-019`'s `POST /ingestion/connectors/{source}/
run`, `GW-018`'s already-existing `POST /reports/generate`), the same
`DownstreamHeadersDep`/`_call_downstream` seam every other tenant-scoped
route in this service already uses -- no new transport mechanism. Both
buttons are only rendered inside the crawl-status panel's already-gated
branch (`crawl_statuses is not none`, i.e. only for a logged-in tenant, same
auth gate DASH-109 established for that panel), and both routes themselves
depend on `DownstreamHeadersDep` (redirect-to-/login on a missing/expired
session), unlike the page's own `OptionalDownstreamHeadersDep` -- an action
route has no "render for an anonymous visitor" case to support, unlike the
read-only page render above.

"No full-page reload" (ticket Implementation acceptance criteria) is
achieved via HTMX (`base.html` already loads `htmx.org`, unused by any route
until this ticket -- not a new dependency, its first real consumer): each
form/button carries `hx-post`/`hx-target`/`hx-swap` attributes and the
handler below returns a small HTML fragment (`_crawl_trigger_result.html` /
`_report_trigger_result.html`, neither extends `base.html`) that HTMX swaps
into a per-action result `<div>` in place, rather than a redirect or a
full-page re-render -- reuses the one client-side mechanism this codebase
already shipped for exactly this "inline re-render" case instead of
inventing a second one (e.g. hand-written `fetch()`/JS).

Failure handling reuses `runs.py`'s `_render_error_for_status` unmodified --
the same generic `error.html` "results currently unavailable" page every
other transport-failure/non-2xx path in this service already renders (DRY
check note, ticket Implementation acceptance criteria: "no new error-handling
pattern"). When HTMX swaps that response into the small result `<div>`, the
visible effect is the same fixed message text, not a second, differently-
worded error surface.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse

from app.dependencies.downstream import (
    DownstreamHeadersDep,
    GatewayApiUrlDep,
    OptionalDownstreamHeadersDep,
)
from app.dependencies.operator_session import (
    OperatorSessionStoreDep,
    cookie_secure,
)
from app.main import templates
from app.routers.runs import _call_downstream, _render_error_for_status

router = APIRouter()

_OPERATOR_SESSION_COOKIE_NAME = "operator_session_id"
_EMPTY_TOKEN_ERROR = "Operator token is required."


@router.get("/operator-login")
def operator_login_form(request: Request):
    return templates.TemplateResponse(request, "operator_login.html", {})


@router.post("/operator-login")
def operator_login_submit(
    request: Request,
    store: OperatorSessionStoreDep,
    operator_token: str = Form(...),
):
    if not operator_token.strip():
        return templates.TemplateResponse(
            request,
            "operator_login.html",
            {"error": _EMPTY_TOKEN_ERROR},
            status_code=422,
        )

    session_id = store.create(operator_token.strip())
    redirect = RedirectResponse(url="/monitoring", status_code=303)
    redirect.set_cookie(
        key=_OPERATOR_SESSION_COOKIE_NAME,
        value=session_id,
        httponly=True,
        samesite="lax",
        secure=cookie_secure(),
    )
    return redirect


def _fetch_crawl_statuses(client: httpx.Client, headers: dict[str, str]) -> list[dict] | None:
    """DASH-109: one row per source the calling tenant has ingested, `{source,
    status, timestamp, row_count}` -- lists sources via `GET /ingestion/
    datasets` (GW-020) then calls `GET /ingestion/connectors/{source}/status`
    (DASH-109's own gateway-api addition) once per source. A transport
    failure or non-200 on the `/ingestion/datasets` call degrades to `None`
    (rendered as the panel's own login-or-unavailable state), matching
    `run_new_form`'s existing "one endpoint's own availability must not
    block the rest of the page" precedent (DASH-108) rather than a second
    failure-handling shape. A single source's own status call failing is
    skipped rather than failing the whole panel, the same "one bad downstream
    must not fail the whole aggregate" principle GW-022's own `system.py`
    already established for the health row above.
    """
    datasets_response, transport_status = _call_downstream(
        client.get, "/ingestion/datasets", headers=headers
    )
    if transport_status is not None or datasets_response.status_code != 200:
        return None

    sources = [item["source"] for item in datasets_response.json()["items"]]

    statuses: list[dict] = []
    for source in sources:
        status_response, status_transport_status = _call_downstream(
            client.get, f"/ingestion/connectors/{source}/status", headers=headers
        )
        if status_transport_status is not None or status_response.status_code != 200:
            continue
        statuses.append({"source": source, **status_response.json()})

    return statuses


@router.get("/monitoring")
def monitoring(request: Request, base_url: GatewayApiUrlDep, headers: OptionalDownstreamHeadersDep):
    """Unauthenticated, matching `GW-022`'s own no-auth design choice for
    `GET /system/health` -- no `require_operator_session`/
    `DownstreamHeadersDep` on this route. `headers` is `None` for an
    anonymous visitor (`OptionalDownstreamHeadersDep`, DASH-109) rather than
    redirecting to `/login`; the "last crawl status" panel below degrades to
    a login prompt in that case (see this module's own docstring, DASH-109's
    auth design decision).
    """
    with httpx.Client(base_url=base_url) as client:
        response, transport_status = _call_downstream(client.get, "/system/health")
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        services = response.json()

        crawl_statuses = _fetch_crawl_statuses(client, headers) if headers is not None else None

    return templates.TemplateResponse(
        request, "monitoring.html", {"services": services, "crawl_statuses": crawl_statuses}
    )


@router.post("/monitoring/connectors/{source}/run")
def trigger_crawl(
    request: Request,
    source: str,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
    since: str = Form(""),
):
    """DASH-110: "run this tenant's crawl now" button, one per source row in
    the crawl-status panel above. Calls `GW-019`'s proxy (`POST /ingestion/
    connectors/{source}/run`) via the same `DownstreamHeadersDep`/
    `_call_downstream` seam every tenant-scoped route in this service already
    uses -- no hand-rolled `Authorization` header, and structurally nothing
    beyond that one outbound `httpx` call (this module's own docstring: no
    container-runtime control surface, no locally spawned OS-level process).
    Returns a small fragment (`_crawl_trigger_result.html`) showing the
    resulting `status`/`row_count` for HTMX to swap into that source row's
    own result `<div>`; any transport failure or non-`202` response reuses
    `_render_error_for_status` unmodified (this module's own docstring, "no
    new error-handling pattern").

    DASH-114: `since` is an optional first-crawl `since` override (`GW-023`),
    forwarded as a query param only when non-blank -- an empty/omitted value
    sends no `since` param at all, matching this route's pre-DASH-114 request
    exactly.
    """
    params = {"since": since} if since.strip() else {}

    with httpx.Client(base_url=base_url) as client:
        response, transport_status = _call_downstream(
            client.post,
            f"/ingestion/connectors/{source}/run",
            params=params,
            headers=headers,
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 202:
            return _render_error_for_status(request, response.status_code)

        result = response.json()

    return templates.TemplateResponse(
        request, "_crawl_trigger_result.html", {"source": source, "result": result}
    )


@router.post("/monitoring/reports/generate")
def trigger_report_generation(
    request: Request,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
    run_id: str = Form(""),
):
    """DASH-110: "generate a report" button/form, one `run_id` text input.
    Calls the already-existing `GW-018` proxy (`POST /reports/generate`) --
    no new reporting capability, this route is a UI trigger only. Same
    `DownstreamHeadersDep`/`_call_downstream` seam as `trigger_crawl` above;
    a blank `run_id` (or any other non-`201` response, e.g. an unknown run
    id) is forwarded to `gateway-api`/`reporting-service` unmodified and
    rendered via `_render_error_for_status`, not re-validated or
    re-interpreted at this layer (same "pass-through UI only" precedent
    `runs.py`'s `run_new_submit` already established for `RunRequest`).
    """
    with httpx.Client(base_url=base_url) as client:
        response, transport_status = _call_downstream(
            client.post, "/reports/generate", json={"run_id": run_id}, headers=headers
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 201:
            return _render_error_for_status(request, response.status_code)

        result = response.json()

    return templates.TemplateResponse(request, "_report_trigger_result.html", {"result": result})
