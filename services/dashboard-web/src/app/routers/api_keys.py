"""ADMIN-005-03: `/api-keys` -- a tenant's own API-key self-service page.

Gated by `DownstreamHeadersDep` (tenant session; redirects to `/login`), never
the operator gate. Calls gateway-api's `GET/POST /me/api-keys` and
`POST /me/api-keys/{key_id}/revoke` (ADMIN-005-02). A downstream `401` (the
session's key was revoked meanwhile) redirects to `/login` too.

The raw key from the mint response is rendered once via the shared
`_one_time_reveal.html` partial, directly from the POST response with
`Cache-Control: no-store`; it is never redirected, logged, or put in the
session store. Revoke renders `_api_key_row.html` as an HTMX fragment
(same mechanism as `settings_tenants.py`). Copy describes keys as
validation-run credentials only.
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Request
from fastapi.responses import RedirectResponse

from app.dependencies.downstream import DownstreamHeadersDep, GatewayApiUrlDep
from app.dependencies.http_client import DOWNSTREAM_HTTP_TIMEOUT_SECONDS
from app.main import templates
from app.routers.runs import _call_downstream, _render_error_for_status

router = APIRouter()

_REVOKE_CONFLICT_MESSAGES = {
    "cannot revoke the key authenticating this request": (
        "This key is in use by your current session and cannot be revoked."
    ),
    "cannot revoke the last active key": (
        "This is your last active key and cannot be revoked. Mint a new key first."
    ),
}
_REVOKE_NOT_FOUND_MESSAGE = "That key was not found."
_REVOKE_GENERIC_CONFLICT_MESSAGE = "This key cannot be revoked."


def _login_redirect() -> RedirectResponse:
    return RedirectResponse("/login", status_code=303)


def _detail(response: httpx.Response) -> str:
    try:
        return str(response.json().get("detail", ""))
    except ValueError:
        return ""


@router.get("/api-keys")
def api_keys_page(request: Request, headers: DownstreamHeadersDep, base_url: GatewayApiUrlDep):
    with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
        response, transport_status = _call_downstream(
            client.get, "/me/api-keys", headers=headers
        )
    if transport_status is not None:
        return _render_error_for_status(request, transport_status)
    if response.status_code == 401:
        return _login_redirect()
    if response.status_code != 200:
        return _render_error_for_status(request, response.status_code)

    return templates.TemplateResponse(
        request, "api_keys.html", {"items": response.json().get("items", [])}
    )


@router.post("/api-keys")
def api_keys_mint(request: Request, headers: DownstreamHeadersDep, base_url: GatewayApiUrlDep):
    with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
        response, transport_status = _call_downstream(
            client.post, "/me/api-keys", headers=headers
        )
    if transport_status is not None:
        return _render_error_for_status(request, transport_status)
    if response.status_code == 401:
        return _login_redirect()
    if response.status_code != 201:
        return _render_error_for_status(request, response.status_code)

    body = response.json()
    result = templates.TemplateResponse(
        request,
        "_api_key_created.html",
        {"name": body["created_at"], "api_key": body["api_key"]},
    )
    result.headers["Cache-Control"] = "no-store"
    return result


@router.post("/api-keys/{key_id}/revoke")
def api_keys_revoke(
    request: Request, key_id: str, headers: DownstreamHeadersDep, base_url: GatewayApiUrlDep
):
    with httpx.Client(base_url=base_url, timeout=DOWNSTREAM_HTTP_TIMEOUT_SECONDS) as client:
        response, transport_status = _call_downstream(
            client.post, f"/me/api-keys/{key_id}/revoke", headers=headers
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code == 401:
            return _login_redirect()
        if response.status_code == 404:
            return templates.TemplateResponse(
                request, "_api_key_revoke_error.html", {"message": _REVOKE_NOT_FOUND_MESSAGE}
            )
        if response.status_code == 409:
            message = _REVOKE_CONFLICT_MESSAGES.get(
                _detail(response), _REVOKE_GENERIC_CONFLICT_MESSAGE
            )
            return templates.TemplateResponse(
                request, "_api_key_revoke_error.html", {"message": message}
            )
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        response, transport_status = _call_downstream(
            client.get, "/me/api-keys", headers=headers
        )
    if transport_status is not None:
        return _render_error_for_status(request, transport_status)
    if response.status_code == 401:
        return _login_redirect()
    if response.status_code != 200:
        return _render_error_for_status(request, response.status_code)

    key = next((k for k in response.json().get("items", []) if k["id"] == key_id), None)
    return templates.TemplateResponse(request, "_api_key_row.html", {"key": key})
