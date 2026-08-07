"""GW-008: proxy router forwarding to `validation-service`'s real `runs`/
`splits` endpoints.

Single responsibility: adapt an authenticated inbound request into exactly
one outbound `httpx` call to `validation-service`, and return its response
unmodified in shape. No split/run/tenant-isolation business logic is
reimplemented here -- that all lives in `validation-service` (VS-006/007/008)
and is forwarded, not duplicated (ticket Design section).

Request/response Pydantic models below are field-for-field copies of
`validation-service`'s own `RunRequest`/`RunResponse`/`RunDetailResponse`
(`services/validation-service/src/app/routers/runs.py`) and
`SplitResultResponse` (`services/validation-service/src/app/routers/
splits.py`), read directly from those files, not guessed -- this is the
public contract clients build against (README.md's "Contract" note).

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

GW-009: `_call_downstream` wraps each of the three outbound `httpx` calls to
translate a *transport*-level failure (connection refused/unreachable ->
`502`, timeout -> `504`) into a generic `HTTPException`, distinct from
`_raise_for_error`'s handling of a normal-but-non-2xx response. A `201`
response with `status: "failed"` in the body is not a transport failure and
never reaches `_call_downstream`'s except clauses -- it is a successful HTTP
response that flows through unmodified, exactly as GW-008 already forwards a
`status: "completed"` response.
"""

from __future__ import annotations

from datetime import datetime

import httpx
from fastapi import APIRouter, Depends, HTTPException
from naive_first_common.tenant_context import TenantContext
from pydantic import BaseModel, Field

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.http_client import ValidationServiceClientDep
from app.dependencies.routing import build_downstream_headers

router = APIRouter()


class RunRequest(BaseModel):
    """Field-for-field copy of validation-service's `RunRequest`
    (`services/validation-service/src/app/routers/runs.py`).
    """

    dataset_id: str
    dataset_reference: dict
    horizon: int = Field(ge=1)
    purge_gap_hours: int = Field(ge=0)
    train_window: int = Field(gt=0)
    test_window: int = Field(gt=0)
    step: int = Field(gt=0)


class RunResponse(BaseModel):
    id: str
    status: str


class RunDetailResponse(BaseModel):
    """Field-for-field copy of validation-service's `RunDetailResponse`."""

    id: str
    tenant_id: str
    dataset_id: str
    horizon: int
    purge_gap_hours: float
    split_config: dict
    status: str
    created_at: datetime
    completed_at: datetime | None
    failure_reason: str | None


class SplitResultResponse(BaseModel):
    """Field-for-field copy of validation-service's `SplitResultResponse`
    (`services/validation-service/src/app/routers/splits.py`).
    """

    split_index: int

    train_start: datetime
    train_end: datetime
    purge_start: datetime | None
    purge_end: datetime | None
    test_start: datetime
    test_end: datetime

    model_mae: float
    model_rmse: float
    model_smape: float
    model_mase: float
    model_da: float
    model_f1: float
    model_oos_r2: float

    naive0_mae: float
    naive0_rmse: float
    naive0_smape: float
    naive0_mase: float
    naive0_da: float
    naive0_f1: float
    naive0_oos_r2: float

    dm_statistic: float
    dm_pvalue: float
    dm_verdict: str


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
    """GW-009: shared transport-failure wrapper for the three proxy calls
    below. Only translates *transport*-level `httpx` exceptions (connection
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
