"""SETUP-015: `/settings/environment` -- operator-facing, read-only panel of
non-secret connectivity facts.

Deliberately a new, disjoint router module (not added to `settings.py`),
mirroring `settings_connectors.py`'s own precedent of one fresh module per
distinct Settings concern.

Gated by `OperatorTokenHeaderDep` (`app.dependencies.operator_session`), the
same gate `/settings/connectors`/`/settings/tenants` already use -- this page
is operator-only, not a tenant page.

DRY check (ticket Design/Analysis section): the only existing env-var reader
this route reuses is `get_gateway_api_url` (`app.dependencies.downstream`,
`GATEWAY_API_URL`) -- no second, differently-named reader of that same value
is introduced. No existing "list all configured service endpoints" helper
existed before this ticket; the literal list below is this ticket's first
one, scoped to non-secret facts only.

No secret env var is ever read by this file, by construction: the only
`os.environ.get`/env-var read anywhere in this module happens inside the
imported `get_gateway_api_url()` (`GATEWAY_API_URL`, a hostname/port --
non-secret). `DATABASE_URL`, `OPERATOR_TOKEN`, any `*_API_KEY`/password env
var, or any per-service internal DB/Redis URL is never read here -- the
per-service entries below are a literal list of env var *names* (strings),
never resolved via `os.environ` at all.

No `@router.post`/`@router.put`/`@router.delete` route exists anywhere in
this file -- read-only is enforced structurally, not by omitting a button
from the template.

Positioning (CLAUDE.md): this page and its template describe the shown facts
as "connectivity"/"environment configuration" only -- never "prediction,"
"forecast," "signal," or "recommendation."
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.dependencies.downstream import GatewayApiUrlDep
from app.dependencies.operator_session import OperatorTokenHeaderDep
from app.main import templates

router = APIRouter()

# Literal list of this platform's known services and the env var *names*
# (never values) that would configure each -- per CLAUDE.md's folder layout
# and implementation-plan.md's build order. `dashboard-web` itself is
# included since it is also configured by env vars an operator may want to
# confirm the name of.
_KNOWN_SERVICES = [
    {
        "name": "gateway-api",
        "env_var_names": ["DATABASE_URL", "OPERATOR_TOKEN"],
    },
    {
        "name": "validation-service",
        "env_var_names": ["DATABASE_URL"],
    },
    {
        "name": "reporting-service",
        "env_var_names": ["DATABASE_URL"],
    },
    {
        "name": "ingestion-service",
        "env_var_names": ["DATABASE_URL"],
    },
    {
        "name": "dashboard-web",
        "env_var_names": ["GATEWAY_API_URL", "DASHBOARD_COOKIE_SECURE"],
    },
]


@router.get("/settings/environment")
def settings_environment(
    request: Request,
    headers: OperatorTokenHeaderDep,
    gateway_api_url: GatewayApiUrlDep,
):
    return templates.TemplateResponse(
        request,
        "settings_environment.html",
        {"services": _KNOWN_SERVICES, "gateway_api_url": gateway_api_url},
    )
