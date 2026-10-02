"""RS-004: the fetch -> render -> persist sequence for a single validation-
audit report, as one named, reusable function.

Single responsibility (ticket's binding decision): call validation-service's
real `GET /runs/{id}` + `GET /runs/{id}/splits`, render via RS-003's Factory
(`kind="validation_audit"`), persist via RS-002's `ReportRepository`, and
return the resulting `ReportRecord`. This is the only place that sequence is
implemented -- `app.routers.report_generation` (RS-004, synchronous HTTP
handler) and RS-006's Redis Streams subscriber (async, no FastAPI request in
scope) both call `generate_validation_audit_report` directly rather than each
re-implementing it (implementation-plan.md section 9 DRY rule).

Exceptions raised here are plain, HTTP-framework-agnostic types (not
`fastapi.HTTPException`) precisely because RS-006's caller is not an HTTP
request handler and must not receive one -- `app.routers.report_generation`
is responsible for translating these into the endpoint's actual HTTP
response, exactly as GW-008/GW-009's own `_raise_for_error`/
`_call_downstream` translate transport failures at the router layer, except
here that translation is pushed one layer further out (into the router) so
this module stays reusable by a non-HTTP caller.
"""

from __future__ import annotations

from typing import Callable

import httpx
from naive_first_common.contracts import (
    RunDetailResponse,
    RunSummaryResponse,
    SplitResultResponse,
)

from app.narrative.client import NarrativeClient
from app.narrative.generation import generate_narrative_html
from app.renderers.base import ReportRenderer, TrendReportRenderer
from app.renderers.factory import get_report_renderer
from app.repositories.interfaces import ReportRecord, ReportRepository

_VALIDATION_AUDIT_KIND = "validation_audit"
_CONSISTENCY_TREND_KIND = "consistency_trend"

# validation-service's GET /runs hard ceiling (`le=100`).
_RUNS_LIST_PAGE_SIZE = 100

# Must equal dashboard-web's MAX_RENDERED_SPLITS (services/dashboard-web/src/
# app/routers/runs.py) so this snapshot's N-of-M matches /runs/trend. Not
# imported: no service imports another service's code.
MAX_RENDERED_SPLITS = 500


class GenerationError(Exception):
    """Base class for every failure `generate_validation_audit_report` can
    raise -- lets a caller (router or RS-006 subscriber) catch broadly if it
    doesn't need to distinguish the specific failure.
    """


class RunNotFoundError(GenerationError):
    """`run_id` does not exist for the resolved tenant, per
    validation-service's own cross-tenant/nonexistent-run 404 (VS-007/
    VS-008) -- both cases collapsed into this one error, no distinction
    surfaced any further out (ticket Design section).
    """

    def __init__(self, run_id: str) -> None:
        super().__init__(f"run {run_id!r} not found")
        self.run_id = run_id


class DownstreamUnavailableError(GenerationError):
    """validation-service was unreachable (connection failure)."""


class DownstreamTimeoutError(GenerationError):
    """validation-service did not respond within the configured timeout."""


class DownstreamResponseError(GenerationError):
    """validation-service responded with an unexpected non-2xx, non-404
    status. No further detail (body/headers) is carried on this exception --
    callers must not leak downstream internals to their own callers.
    """


def _call_downstream(fn: Callable[..., httpx.Response], *args, **kwargs) -> httpx.Response:
    try:
        return fn(*args, **kwargs)
    except httpx.ConnectError as exc:
        raise DownstreamUnavailableError() from exc
    except httpx.TimeoutException as exc:
        raise DownstreamTimeoutError() from exc


def _raise_for_error(response: httpx.Response, run_id: str) -> None:
    if response.status_code == 404:
        raise RunNotFoundError(run_id)
    if response.status_code >= 400:
        raise DownstreamResponseError()


def generate_validation_audit_report(
    tenant_id: str,
    run_id: str,
    client: httpx.Client,
    repository: ReportRepository,
    renderer_factory: Callable[[str], ReportRenderer] = get_report_renderer,
    narrative_client: NarrativeClient | None = None,
) -> ReportRecord:
    """Fetches `run_id`'s detail + splits from validation-service (scoped to
    `tenant_id` via the `X-Tenant-Id` header, sourced only from the caller's
    already-resolved tenant identity -- never a raw inbound header value),
    renders a `"validation_audit"` report, and persists it.

    `narrative_client` (AI-002, default `None`): when provided, an
    AI-generated narrative paragraph is generated (fact-checked, gracefully
    degrading to no narrative on any failure) and rendered alongside the
    table. Default `None` keeps every existing caller -- in particular
    `POST /reports/generate`'s router -- byte-identical to pre-AI-002
    behavior; only `app.subscriber`'s `run.completed` event handler passes a
    real client.
    """
    headers = {"X-Tenant-Id": tenant_id}

    run_response = _call_downstream(client.get, f"/runs/{run_id}", headers=headers)
    _raise_for_error(run_response, run_id)
    run = RunDetailResponse(**run_response.json())

    splits_response = _call_downstream(client.get, f"/runs/{run_id}/splits", headers=headers)
    _raise_for_error(splits_response, run_id)
    splits = [SplitResultResponse(**item) for item in splits_response.json()]

    narrative_html = None
    if narrative_client is not None:
        narrative_html = generate_narrative_html(run, splits, narrative_client)

    renderer = renderer_factory(_VALIDATION_AUDIT_KIND)
    content = renderer.render(run, splits, narrative_html=narrative_html)

    return repository.create_report(
        tenant_id=tenant_id,
        run_id=run_id,
        report_kind=_VALIDATION_AUDIT_KIND,
        content=content,
        status="generated",
    )


def _fetch_completed_runs(
    client: httpx.Client, headers: dict[str, str], dataset_id: str, horizon: int
) -> list[RunSummaryResponse]:
    runs: list[RunSummaryResponse] = []
    offset = 0
    while True:
        response = _call_downstream(
            client.get,
            "/runs",
            headers=headers,
            params={"limit": _RUNS_LIST_PAGE_SIZE, "offset": offset},
        )
        if response.status_code >= 400:
            raise DownstreamResponseError()
        body = response.json()
        page = [RunSummaryResponse(**item) for item in body["items"]]
        runs.extend(page)
        offset += _RUNS_LIST_PAGE_SIZE
        if len(page) < _RUNS_LIST_PAGE_SIZE or offset >= body["total"]:
            break
    return [
        run
        for run in runs
        if run.dataset_id == dataset_id and run.horizon == horizon and run.status == "completed"
    ]


def _fetch_bounded_splits(
    client: httpx.Client, headers: dict[str, str], run_id: str
) -> list[SplitResultResponse]:
    """Most recent `MAX_RENDERED_SPLITS` splits: count first, then offset =
    max(0, total - cap), same tail rule as dashboard-web.
    """
    count_response = _call_downstream(client.get, f"/runs/{run_id}/splits/count", headers=headers)
    if count_response.status_code >= 400:
        raise DownstreamResponseError()
    total = count_response.json()["total"]

    splits_response = _call_downstream(
        client.get,
        f"/runs/{run_id}/splits",
        headers=headers,
        params={"limit": MAX_RENDERED_SPLITS, "offset": max(0, total - MAX_RENDERED_SPLITS)},
    )
    if splits_response.status_code >= 400:
        raise DownstreamResponseError()
    return [SplitResultResponse(**item) for item in splits_response.json()]


def consistency_trend_scope_key(dataset_id: str, horizon: int) -> str:
    return f"{_CONSISTENCY_TREND_KIND}:{dataset_id}:{horizon}"


def generate_consistency_trend_report(
    tenant_id: str,
    dataset_id: str,
    horizon: int,
    client: httpx.Client,
    repository: ReportRepository,
    renderer_factory: Callable[[str], TrendReportRenderer] = get_report_renderer,
) -> ReportRecord:
    """RPT-002-02: snapshot of "beat Naive0 in N of M completed runs" for one
    (dataset_id, horizon) group, read from validation-service's `GET /runs`
    and splits endpoints with `X-Tenant-Id`. A group with no completed runs
    still persists a report (the renderer's no-data state).
    """
    headers = {"X-Tenant-Id": tenant_id}
    runs = _fetch_completed_runs(client, headers, dataset_id, horizon)
    runs_with_splits = [(run, _fetch_bounded_splits(client, headers, run.id)) for run in runs]

    content = renderer_factory(_CONSISTENCY_TREND_KIND).render(dataset_id, horizon, runs_with_splits)

    return repository.create_report(
        tenant_id=tenant_id,
        run_id=consistency_trend_scope_key(dataset_id, horizon),
        report_kind=_CONSISTENCY_TREND_KIND,
        content=content,
        status="generated",
    )
