"""GW-008: proxy router forwarding to `validation-service`'s real `runs`/
`splits` endpoints.

Single responsibility: adapt an authenticated inbound request into exactly
one outbound `httpx` call to `validation-service`, and return its response
unmodified in shape. No split/run/tenant-isolation business logic is
reimplemented here -- that all lives in `validation-service` (VS-006/007/008)
and is forwarded, not duplicated (ticket Design section).

Request/response Pydantic models (`RunRequest`/`RunResponse`/
`RunDetailResponse`/`SplitResultResponse`) are imported from
`naive_first_common.contracts` (ARCH-003) -- the shared wire-contract module
both this router and `validation-service`'s `routers/runs.py`/`routers/
splits.py` import from, so there is exactly one definition instead of a
hand-synced copy. This is the public contract clients build against
(README.md's "Contract" note).

Handler flow (fixed, ticket Design section, must match exactly): resolve
`tenant: TenantContext = Depends(get_authenticated_tenant)` (GW-006) ->
`headers = build_downstream_headers(tenant)` (GW-007) -> forward via
`httpx` to `VALIDATION_SERVICE_URL` + the matching validation-service path
-> return validation-service's response body/status, parsed into this
router's own (identical) Pydantic models rather than proxied as raw bytes,
so FastAPI's own response validation/OpenAPI contract stays accurate.

No tenant-isolation branching is added in this router -- the `404` a
cross-tenant request receives is entirely validation-service's own
`get_run`-returns-`None`-for-both-cases behavior (VS-007/VS-008), forwarded
as-is via `_raise_for_status`.

GW-009: `_call_downstream` wraps each of the outbound `httpx` calls to
translate a *transport*-level failure (connection refused/unreachable ->
`502`, timeout -> `504`) into a generic `HTTPException`, distinct from
`_raise_for_error`'s handling of a normal-but-non-2xx response. A `201`
response with `status: "failed"` in the body is not a transport failure and
never reaches `_call_downstream`'s except clauses -- it is a successful HTTP
response that flows through unmodified, exactly as GW-008 already forwards a
`status: "completed"` response.

GW-016: `GET /runs` follows the exact same handler flow as the three
existing proxy handlers -- resolve tenant -> build headers -> forward via
`_call_downstream`/`_raise_for_error` -> return unmodified. `limit`/`offset`
query params are forwarded to `validation-service` unmodified; no
pagination/ordering is reimplemented here (that's VS-022's `list_runs`'s
job). `RunSummaryResponse` (the `items` element shape) is imported from
`naive_first_common.contracts` (VS-022/ARCH-003), never redefined; the
`{items, limit, offset, total}` envelope around it (`RunListResponse`) is
this router's own local wire shape, matching `validation-service`'s own
envelope field names exactly since this is pass-through, not
reimplementation (same precedent as `RunResponse`/`RunDetailResponse`/
`SplitResultResponse` being this router's own Pydantic models even though
they're field-for-field copies of validation-service's).
"""

from __future__ import annotations

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from naive_first_common.contracts import (
    RunDetailResponse,
    RunRequest,
    RunResponse,
    RunSummaryResponse,
    SplitResultResponse,
)
from naive_first_common.tenant_context import TenantContext
from pydantic import BaseModel

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.http_client import ValidationServiceClientDep
from app.dependencies.routing import build_downstream_headers

router = APIRouter()


class RunListResponse(BaseModel):
    """Response envelope for `GET /runs` (GW-016): mirrors
    `validation-service`'s own `RunListResponse` envelope field-for-field
    (`services/validation-service/src/app/routers/runs.py`) since this is a
    pass-through proxy, not a reimplementation. `items` uses
    `RunSummaryResponse`, imported from `naive_first_common.contracts`
    (VS-022/ARCH-003) -- never redefined here. This envelope shape itself is
    local to this router, not a shared contract type -- matching the
    existing precedent of `RunResponse`/`RunDetailResponse`/
    `SplitResultResponse` above.
    """

    items: list[RunSummaryResponse]
    limit: int
    offset: int
    total: int


def _raise_for_error(response: httpx.Response) -> None:
    """Forwards a non-2xx validation-service response as-is (same status
    code, same detail) -- this is pass-through, not new tenant-isolation
    logic. The cross-tenant/nonexistent-run `404` (VS-007/VS-008) reaches
    the caller unchanged.
    """
    if response.status_code >= 400:
        try:
            detail = response.json().get("detail", response.text)
        except ValueError:
            detail = response.text
        raise HTTPException(status_code=response.status_code, detail=detail)


def _call_downstream(fn, *args, **kwargs) -> httpx.Response:
    """GW-009: shared transport-failure wrapper for the proxy calls below.
    Only translates *transport*-level `httpx` exceptions (connection
    refused/unreachable, timeout) into `502`/`504` -- a normal response
    (including validation-service's own `201`+`status:"failed"`) is not an
    exception and never reaches this except block, so it passes through
    unmodified via the caller's existing `_raise_for_error` path (ticket
    Design section, explicit non-goal).

    Bodies are generic on purpose: no hostname/URL/`str(exc)` is included,
    so a downstream address is never leaked to a gateway client.
    """
    try:
        return fn(*args, **kwargs)
    except httpx.ConnectError as exc:
        raise HTTPException(status_code=502, detail="downstream service unavailable") from exc
    except httpx.TimeoutException as exc:
        raise HTTPException(status_code=504, detail="downstream service timed out") from exc


@router.post("/runs", response_model=RunResponse, status_code=201)
def create_run(
    request: RunRequest,
    client: ValidationServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
) -> RunResponse:
    headers = build_downstream_headers(tenant)
    response = _call_downstream(
        client.post, "/runs", json=request.model_dump(), headers=headers
    )
    _raise_for_error(response)
    return RunResponse(**response.json())


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    client: ValidationServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
    limit: int = Query(default=20),
    offset: int = Query(default=0),
) -> RunListResponse:
    headers = build_downstream_headers(tenant)
    response = _call_downstream(
        client.get, "/runs", params={"limit": limit, "offset": offset}, headers=headers
    )
    _raise_for_error(response)
    return RunListResponse(**response.json())


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(
    run_id: str,
    client: ValidationServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
) -> RunDetailResponse:
    headers = build_downstream_headers(tenant)
    response = _call_downstream(client.get, f"/runs/{run_id}", headers=headers)
    _raise_for_error(response)
    return RunDetailResponse(**response.json())


@router.get("/runs/{run_id}/splits", response_model=list[SplitResultResponse])
def get_splits(
    run_id: str,
    client: ValidationServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
) -> list[SplitResultResponse]:
    headers = build_downstream_headers(tenant)
    response = _call_downstream(client.get, f"/runs/{run_id}/splits", headers=headers)
    _raise_for_error(response)
    return [SplitResultResponse(**item) for item in response.json()]
