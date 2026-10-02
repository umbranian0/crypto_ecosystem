"""GW-018: proxy router forwarding to `reporting-service`'s real `POST
/reports/generate` (RS-004) and `GET /reports/{id}` (RS-005) endpoints.

Deliberately a new module, not added to `runs.py` -- `reports.py` proxies a
different downstream service entirely (`reporting-service`, not
`validation-service`), and keeping it separate avoids any file overlap with
GW-016's `runs.py` edit (ticket Design section, binding sequencing
constraint). This ticket does not touch `runs.py` at all.

Single responsibility, same as `runs.py`: adapt an authenticated inbound
request into exactly one outbound `httpx` call to `reporting-service`, and
return its response unmodified in shape. No report-generation/rendering or
tenant-isolation logic is reimplemented here -- that all lives in
`reporting-service` (RS-002/RS-004/RS-005) and is forwarded, not duplicated.

Request/response Pydantic models (`GenerateReportRequest`/
`GenerateReportResponse`/`ReportDetailResponse`) are field-for-field copies of
`reporting-service`'s real ones (`services/reporting-service/src/app/routers/
report_generation.py`/`report_retrieval.py`), defined locally in this router
rather than added to `naive_first_common.contracts` this sprint -- out of
scope (ticket Design section): `reporting-service` has no existing shared-
contract dependency on `naive_first_common.contracts` for its report models
to hang off of, unlike `validation-service`'s `RunRequest`/etc (ARCH-003).
This is a version-sync point, not an independent contract: if
`reporting-service`'s models change, these must be updated to match, same
caveat GW-008's original pre-ARCH-003 approach carried. RPT-002-03: the
request model now mirrors reporting-service's `kind`/`run_id`/`dataset_id`/
`horizon` shape (types only; the per-kind field-combination validation stays
downstream and its 422 passes through `_raise_for_error`). Only fields the
caller actually sent are forwarded, so a legacy `{run_id}` body still
forwards exactly `{"run_id": ...}`.

Handler flow (fixed, mirrors GW-008/GW-016 exactly): resolve
`tenant: TenantContext = Depends(get_authenticated_tenant)` (GW-006) ->
`headers = build_downstream_headers(tenant)` (GW-007, reused as-is) ->
forward via `httpx` to `REPORTING_SERVICE_URL` -> return the response
unmodified in shape and status code.

DRY note (ticket Design/DRY-check section): `_call_downstream`/
`_raise_for_error` already exist as module-level functions in `runs.py`
(GW-008/GW-009). Since this ticket is explicitly barred from touching
`runs.py` (binding sequencing constraint against colliding with GW-016), the
"extract to a shared module" option would itself require editing `runs.py`
to import from that shared module -- which is exactly the forbidden edit.
The only way to reuse (not duplicate) that logic without touching `runs.py`
is to import the two functions directly from it, which is what this module
does below. There is no circular import: `runs.py` only imports from
`app.dependencies.*`, never from `app.routers.reports`.

No tenant-isolation branching is added in this router -- the `404` a
cross-tenant `GET /reports/{id}` request receives is entirely
`reporting-service`'s own `get_report`-returns-`None`-for-both-cases
behavior (RS-002/RS-005), forwarded as-is via `_raise_for_error`.
"""

from __future__ import annotations

from datetime import datetime
from typing import Literal

from fastapi import APIRouter, Depends, Response
from fastapi.responses import JSONResponse
from naive_first_common.tenant_context import TenantContext
from pydantic import BaseModel

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.http_client import ReportingServiceClientDep
from app.dependencies.routing import build_downstream_headers
from app.routers.runs import _call_downstream, _raise_for_error

router = APIRouter()


class GenerateReportRequest(BaseModel):
    kind: Literal["validation_audit", "consistency_trend"] = "validation_audit"
    run_id: str | None = None
    dataset_id: str | None = None
    horizon: int | None = None


class GenerateReportResponse(BaseModel):
    id: str
    status: str


class ReportDetailResponse(BaseModel):
    id: str
    run_id: str
    report_kind: str
    generated_at: datetime
    status: str
    content: str


@router.post("/reports/generate", response_model=GenerateReportResponse, status_code=201)
def generate_report(
    request: GenerateReportRequest,
    client: ReportingServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
) -> GenerateReportResponse:
    headers = build_downstream_headers(tenant)
    response = _call_downstream(
        client.post, "/reports/generate", json=request.model_dump(exclude_unset=True), headers=headers
    )
    _raise_for_error(response)
    return GenerateReportResponse(**response.json())


@router.get("/reports/{report_id}/diff/{other_id}")
def diff_reports(
    report_id: str,
    other_id: str,
    client: ReportingServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
) -> JSONResponse:
    """RPT-004-02: pass-through of reporting-service's report diff. The diff
    shape is owned by reporting-service, so the JSON body is returned as-is
    rather than mirrored in a local model; 404/422 come via `_raise_for_error`.
    """
    headers = build_downstream_headers(tenant)
    response = _call_downstream(client.get, f"/reports/{report_id}/diff/{other_id}", headers=headers)
    _raise_for_error(response)
    return JSONResponse(response.json())


@router.get("/reports/{report_id}", response_model=ReportDetailResponse)
def get_report(
    report_id: str,
    client: ReportingServiceClientDep,
    tenant: TenantContext = Depends(get_authenticated_tenant),
    format: str | None = None,
) -> ReportDetailResponse | Response:
    """JSON by default. `?format=pdf` (RPT-001-03) is a byte pass-through:
    the format value is validated downstream (a bad value surfaces as
    reporting-service's own 422) and the body is never inspected here.
    """
    headers = build_downstream_headers(tenant)
    if format is None:
        response = _call_downstream(client.get, f"/reports/{report_id}", headers=headers)
        _raise_for_error(response)
        return ReportDetailResponse(**response.json())

    response = _call_downstream(
        client.get, f"/reports/{report_id}", headers=headers, params={"format": format}
    )
    _raise_for_error(response)
    passthrough_headers = {}
    if "content-disposition" in response.headers:
        passthrough_headers["Content-Disposition"] = response.headers["content-disposition"]
    return Response(
        content=response.content,
        media_type="application/pdf",
        headers=passthrough_headers,
    )
