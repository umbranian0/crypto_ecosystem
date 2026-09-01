"""DASH-112: `/settings/connectors` -- operator-facing, per-tenant connector
credential-status lookup.

Revised-scope ticket (per `docs/sprints/sprint-18.md`'s UAT addendum): a
per-tenant lookup, not a cross-tenant aggregate -- an operator supplies a
`tenant_id` explicitly (no tenant directory/dropdown exists this sprint,
`SETUP-011`'s full tenant-list UI remains out of scope). Deliberately a new,
disjoint router module (not added to `operator.py`), mirroring that file's
own precedent of one fresh module per distinct concern.

Gated by `require_operator_session` (`DASH-113`) via `OperatorTokenHeaderDep`
(`app.dependencies.operator_session`, DASH-112 addition) -- that dependency
calls `require_operator_session` itself before resolving the operator's
session-stored raw token into the `X-Operator-Token` header
`get_authenticated_operator` (gateway-api, GW-021) expects, so this route
never hand-rolls its own cookie read/store lookup a second time. A tenant's
own `session_id` cookie is never read here, so it can never satisfy this
gate.

DRY check (ticket Design section): calls `INGEST-012`'s patched `GW-021`
proxy (`GET /ingestion/connectors/credentials-status`) directly -- no second
credential-status query invented. Reuses `runs.py`'s `_call_downstream`/
`_render_error_for_status` for the transport-failure/non-200 path, the same
DRY-reuse `operator.py`'s `/monitoring` route already established, rather
than a third near-identical try/except.

`tenant_id` is read as an optional query parameter distinguishing three
cases: (1) no `tenant_id` param at all -- the initial, unsubmitted form
render, no error shown; (2) a present but blank/whitespace-only value -- a
submission, redisplayed with a "enter a tenant id" `422` error, never a raw
passthrough; (3) a non-blank value -- forwarded to gateway-api unmodified.
An unrecognized tenant id is not a distinguishable case at this layer: the
proxied endpoint itself returns a normal `200` with per-source
`credential_set=False` entries for a tenant with no stored credentials
(`ingestion-service`'s own "empty is a valid answer" convention,
`CredentialRepository.get_credential_status`) -- so this route needs no
special-case handling for "unknown tenant," it renders whatever `items` list
comes back.

No `@router.post` route exists anywhere in this file (ticket Implementation
acceptance criteria, Review acceptance criteria) -- an operator uses
`services/ingestion-service/scripts/set_connector_credentials.py` (CLI) to
write a credential in the meantime; this page never grows a write form.

Positioning (CLAUDE.md): this page and its template describe the lookup as
"connector credential status" only -- never "prediction," "forecast,"
"signal," or "recommendation."
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request

from app.dependencies.downstream import GatewayApiUrlDep
from app.dependencies.operator_session import OperatorTokenHeaderDep
from app.main import templates
from app.routers.runs import _call_downstream, _render_error_for_status

router = APIRouter()

_MISSING_TENANT_ID_ERROR = "Enter a tenant id."


@router.get("/settings/connectors")
def connectors_credentials_status(
    request: Request,
    headers: OperatorTokenHeaderDep,
    base_url: GatewayApiUrlDep,
    tenant_id: str | None = None,
):
    if tenant_id is None:
        return templates.TemplateResponse(request, "settings_connectors.html", {})

    tenant_id = tenant_id.strip()
    if not tenant_id:
        return templates.TemplateResponse(
            request,
            "settings_connectors.html",
            {"error": _MISSING_TENANT_ID_ERROR},
            status_code=422,
        )

    with httpx.Client(base_url=base_url) as client:
        response, transport_status = _call_downstream(
            client.get,
            "/ingestion/connectors/credentials-status",
            headers=headers,
            params={"tenant_id": tenant_id},
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        items = response.json().get("items", [])

    return templates.TemplateResponse(
        request, "settings_connectors.html", {"items": items, "tenant_id": tenant_id}
    )
