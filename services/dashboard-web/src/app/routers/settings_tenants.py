"""SETUP-012: `/settings/tenants` -- operator-only tenant/API-key management.

Deliberately a new, disjoint router module (not added to `settings.py`),
mirroring that file's own precedent of one fresh module per distinct Settings
concern -- this ticket's own diff never touches `settings.py`.

Gated by `require_operator_session` (`DASH-113`) via `OperatorTokenHeaderDep`
(`app.dependencies.operator_session`), the same seam `settings.py`'s
`/settings/connectors` (DASH-112) already uses -- a tenant's own `session_id`
cookie is never read here, so it can never satisfy this gate.

Calls `SETUP-011`'s new gateway-api tenant-admin endpoints directly (`GET
/tenants`, `POST /tenants`, `POST /tenants/{tenant_id}/api-keys/{key_id}/
revoke`) -- no second tenant-admin surface invented. Reuses `runs.py`'s
`_call_downstream`/`_render_error_for_status` for the transport-failure/
non-2xx path, the same DRY-reuse `settings.py`'s `/settings/connectors`
already established, rather than a fourth near-identical try/except.

**One-time-reveal**: "create tenant" renders the shared
`_one_time_reveal.html` partial (extracted from `SETUP-003`'s own
`setup_key_reveal.html` markup by this ticket) with `label="Tenant"` and a
"Back to tenants" continue link -- not a second near-identical confirmation
block.

**Revoke as an HTMX fragment**: `POST /settings/tenants/{tenant_id}/
api-keys/{key_id}/revoke` renders `_tenant_row.html`, the same per-tenant row
markup `settings_tenants.html`'s own table body uses (`{% include %}`, not a
copy), so the swapped-in fragment and a fresh full-page `GET` render
identically -- reusing `operator.py`'s (`DASH-110`) established
`hx-post`/`hx-target`/`hx-swap="outerHTML"` mechanism, not reinvented.

Positioning (CLAUDE.md): this page and its templates describe tenants/keys
as validation-run access credentials only -- never "prediction," "forecast,"
"signal," or "recommendation."
"""

from __future__ import annotations

from fastapi import APIRouter, Form, Request

from app.dependencies.downstream import GatewayApiUrlDep
from app.dependencies.http_client import DOWNSTREAM_HTTP_TIMEOUT_SECONDS
from app.dependencies.operator_session import OperatorTokenHeaderDep
from app.main import templates
from app.routers.runs import _call_downstream, _render_error_for_status

import httpx

router = APIRouter()

_MISSING_TENANT_NAME_ERROR = "Enter a tenant name."


def _fetch_tenants(client: httpx.Client, headers: dict[str, str]):
    response, transport_status = _call_downstream(client.get, "/tenants", headers=headers)
    return response, transport_status


@router.get("/settings/tenants")
def settings_tenants(request: Request, headers: OperatorTokenHeaderDep, base_url: GatewayApiUrlDep):
    with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
        response, transport_status = _fetch_tenants(client, headers)
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        items = response.json().get("items", [])

    return templates.TemplateResponse(request, "settings_tenants.html", {"items": items})


@router.post("/settings/tenants")
def settings_tenants_create(
    request: Request,
    headers: OperatorTokenHeaderDep,
    base_url: GatewayApiUrlDep,
    tenant_name: str = Form(...),
):
    tenant_name = tenant_name.strip()
    if not tenant_name:
        with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
            response, transport_status = _fetch_tenants(client, headers)
            if transport_status is not None:
                return _render_error_for_status(request, transport_status)
            if response.status_code != 200:
                return _render_error_for_status(request, response.status_code)
            items = response.json().get("items", [])

        return templates.TemplateResponse(
            request,
            "settings_tenants.html",
            {"items": items, "error": _MISSING_TENANT_NAME_ERROR},
            status_code=422,
        )

    with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
        response, transport_status = _call_downstream(
            client.post, "/tenants", headers=headers, json={"tenant_name": tenant_name}
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 201:
            return _render_error_for_status(request, response.status_code)

        body = response.json()

    return templates.TemplateResponse(
        request,
        "_settings_tenant_created.html",
        {"tenant_name": body["tenant_name"], "api_key": body["api_key"]},
    )


@router.post("/settings/tenants/{tenant_id}/api-keys/{key_id}/revoke")
def settings_tenants_revoke_api_key(
    request: Request,
    tenant_id: str,
    key_id: str,
    headers: OperatorTokenHeaderDep,
    base_url: GatewayApiUrlDep,
):
    with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
        response, transport_status = _call_downstream(
            client.post, f"/tenants/{tenant_id}/api-keys/{key_id}/revoke", headers=headers
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        response, transport_status = _fetch_tenants(client, headers)
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        items = response.json().get("items", [])
        tenant = next((item for item in items if item["id"] == tenant_id), None)

    return templates.TemplateResponse(request, "_tenant_row.html", {"tenant": tenant})
