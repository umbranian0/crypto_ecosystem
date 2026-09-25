"""ADMIN-002-02: `/settings/audit-log` -- operator-only, read-only operator
action history (audit trail) surface.

Deliberately a new, disjoint router module (not added to `settings.py`,
`settings_tenants.py`, or `settings_connectors.py`), mirroring those files'
own "one new disjoint file per Settings concern" precedent.

Gated by `OperatorTokenHeaderDep` (`app.dependencies.operator_session`,
`DASH-113`), the same seam every other `/settings/*` route already uses -- a
tenant's own `session_id` cookie is never read here, so it can never satisfy
this gate.

Calls `ADMIN-002-01`'s new gateway-api `GET /operator-audit-log` directly --
no second audit-log surface invented. Reuses `runs.py`'s
`_call_downstream`/`_render_error_for_status` for the transport-failure/
non-200 path, the same DRY-reuse every other Settings route already
established, rather than a fourth near-identical try/except.

`limit`/`offset` query params are forwarded to gateway-api unmodified,
defaulting to `20`/`0` (matching the backend's own defaults) -- not
re-validated at this layer.

No `@router.post` route exists anywhere in this file -- this is a read-only
surface by design (the AC's own "read-only" wording); no mutating control of
any kind is ever rendered here.

Positioning (CLAUDE.md): this page and its template describe the rendered
rows as "operator action history"/"audit trail" only -- never "prediction,"
"forecast," "signal," or "recommendation."
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request

from app.dependencies.downstream import GatewayApiUrlDep
from app.dependencies.http_client import DOWNSTREAM_HTTP_TIMEOUT_SECONDS
from app.dependencies.operator_session import OperatorTokenHeaderDep
from app.main import templates
from app.routers.runs import _call_downstream, _render_error_for_status

router = APIRouter()


@router.get("/settings/audit-log")
def settings_audit_log(
    request: Request,
    headers: OperatorTokenHeaderDep,
    base_url: GatewayApiUrlDep,
    limit: int = 20,
    offset: int = 0,
):
    with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
        response, transport_status = _call_downstream(
            client.get,
            "/operator-audit-log",
            headers=headers,
            params={"limit": limit, "offset": offset},
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        body = response.json()

    return templates.TemplateResponse(
        request,
        "settings_audit_log.html",
        {"items": body["items"], "limit": body["limit"], "offset": body["offset"], "total": body["total"]},
    )
