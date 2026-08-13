"""DASH-004: run detail view (status + per-split results).

Single responsibility: `GET /runs/{run_id}` calls gateway-api's
`GET /runs/{id}` and, on a successful detail fetch, `GET /runs/{id}/splits`
(unconditionally -- a `"running"` run legitimately has zero splits yet, so
whether any exist is decided by the splits endpoint's own response, not a
client-side status guess), then renders `run_detail.html` with both.

Pattern: Dependency Injection only (implementation-plan.md section 7) -- no
Strategy/Factory/Adapter applies to a read-only detail view. `headers:
DownstreamHeadersDep`/`base_url: GatewayApiUrlDep` (DASH-003) are the sole
source of the outbound `Authorization` header and target host; this module
never hand-rolls either.

Response shapes are parsed via `naive_first_common.contracts`' shared
`RunDetailResponse`/`SplitResultResponse` (ARCH-003) -- the same models
`gateway-api` itself uses -- rather than a fourth hand-duplicated copy of the
field list (ticket Analysis section).

Failure handling: gateway-api's `404` (nonexistent or cross-tenant, both
collapsed upstream per GW-008) renders `not_found.html`, no distinction
shown. A transport-level `httpx.ConnectError`/`httpx.TimeoutException`, or a
`502`/`504` status forwarded from gateway-api (GW-009's own transport-failure
translation), renders `error.html` with a fixed generic "results currently
unavailable" message -- no hostname/status/exception text leaked into the
page. Both templates are intentionally generic/reusable, not detail-specific
-- DASH-006 reuses `error.html` for its own transport-failure handling per
implementation-plan.md section 9's DRY rule.

Positioning: `run_detail.html`'s copy describes the shown numbers as
"validation results" / "benchmark comparison" / "per-split metrics," never
"prediction," "forecast," "signal," or "recommendation" (CLAUDE.md's core
positioning constraint) -- this is the first template that renders real
model output.

DASH-006: `GET /runs/new` (pure static form render, no downstream call) and
`POST /runs/new` (submit-a-run), added to this same router module (sequential
edit after DASH-004, per sprint-11.md's sequencing decision). Declared
*before* `GET /runs/{run_id}` below -- FastAPI/Starlette match routes in
registration order, so `/runs/new` must precede the `/runs/{run_id}` path
pattern or the latter would swallow it (`run_id="new"`). `_call_downstream`
below is `_fetch`'s DASH-004 name generalized to take any bound `httpx.Client`
method (`client.get` or `client.post`) instead of being GET-only, so the new
`POST /runs` call reuses the exact same transport-failure translation instead
of a second near-identical try/except (implementation-plan.md section 9 DRY
rule, checked against this file before writing per this ticket's own DRY
check note).

`dataset_reference`'s two interim modes (`{"path": ...}` / `{"inline": ...}`)
are copied verbatim from `services/validation-service/src/app/dataset_source.py`'s
`InlineOrLocalFileDatasetSource.load` -- not approximated. The form never
pre-fills `purge_gap_hours` (or any other field) with a default value, and the
handler never substitutes/overrides a submitted value with one of its own --
this is pass-through UI only, so no field/default here can cause a submitted
run to skip the purge gap or the mandatory naive baselines (CLAUDE.md,
restated in this ticket's Design section as its single highest-stakes
constraint). `RunRequest` construction is the only validation performed
client-side of gateway-api itself; a `422` gateway-api itself returns is
forwarded verbatim, not reinterpreted.
"""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from naive_first_common.contracts import (
    RunDetailResponse,
    RunRequest,
    RunResponse,
    SplitResultResponse,
)
from pydantic import ValidationError

from app.dependencies.downstream import DownstreamHeadersDep, GatewayApiUrlDep
from app.main import templates

router = APIRouter()

_UNAVAILABLE_ERROR = "results currently unavailable"
_MISSING_DATASET_REFERENCE_ERROR = (
    "Provide either a local file path or an inline payload for the dataset reference."
)
_INVALID_INLINE_JSON_ERROR = "Inline payload must be valid JSON."


def _call_downstream(fn, *args, **kwargs) -> tuple[httpx.Response | None, int | None]:
    """Issues one outbound call via a bound `httpx.Client` method (`client.get`
    or `client.post`), translating a transport-level failure into a
    `(None, status_code)` pair instead of letting the exception propagate --
    mirrors gateway-api's own GW-009 `_call_downstream` translation
    (`ConnectError` -> 502, `TimeoutException` -> 504), one hop further down
    the chain. A normal (including non-2xx) response is returned unchanged
    for the caller to interpret.
    """
    try:
        return fn(*args, **kwargs), None
    except httpx.ConnectError:
        return None, 502
    except httpx.TimeoutException:
        return None, 504


@router.get("/runs/new")
def run_new_form(request: Request, headers: DownstreamHeadersDep):
    """`headers` is unused beyond enforcing DASH-003's session check -- this
    route makes no downstream call (pure static form render), but a run
    submission form is only reachable once logged in, matching `POST /login`'s
    own redirect target (DASH-002).
    """
    return templates.TemplateResponse(request, "run_new.html", {})


def _extract_detail(response: httpx.Response) -> str:
    """Forwards gateway-api's own `422` validation-error body as-is (same
    spirit as gateway-api's own `_raise_for_error`) -- never a hand-written
    re-derivation of gateway-api's/`RunRequest`'s validation rules.
    """
    try:
        return str(response.json().get("detail", response.text))
    except ValueError:
        return response.text


@router.post("/runs/new")
def run_new_submit(
    request: Request,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
    dataset_id: str = Form(""),
    dataset_reference_path: str = Form(""),
    dataset_reference_inline: str = Form(""),
    horizon: str = Form(""),
    purge_gap_hours: str = Form(""),
    train_window: str = Form(""),
    test_window: str = Form(""),
    step: str = Form(""),
):
    values = {
        "dataset_id": dataset_id,
        "dataset_reference_path": dataset_reference_path,
        "dataset_reference_inline": dataset_reference_inline,
        "horizon": horizon,
        "purge_gap_hours": purge_gap_hours,
        "train_window": train_window,
        "test_window": test_window,
        "step": step,
    }

    if dataset_reference_path.strip():
        dataset_reference: dict = {"path": dataset_reference_path.strip()}
    elif dataset_reference_inline.strip():
        try:
            dataset_reference = {"inline": json.loads(dataset_reference_inline)}
        except json.JSONDecodeError:
            return templates.TemplateResponse(
                request,
                "run_new.html",
                {"error": _INVALID_INLINE_JSON_ERROR, "values": values},
                status_code=422,
            )
    else:
        return templates.TemplateResponse(
            request,
            "run_new.html",
            {"error": _MISSING_DATASET_REFERENCE_ERROR, "values": values},
            status_code=422,
        )

    try:
        run_request = RunRequest(
            dataset_id=dataset_id,
            dataset_reference=dataset_reference,
            horizon=int(horizon),
            purge_gap_hours=int(purge_gap_hours),
            train_window=int(train_window),
            test_window=int(test_window),
            step=int(step),
        )
    except (ValueError, ValidationError) as exc:
        return templates.TemplateResponse(
            request,
            "run_new.html",
            {"error": str(exc), "values": values},
            status_code=422,
        )

    with httpx.Client(base_url=base_url) as client:
        response, transport_status = _call_downstream(
            client.post, "/runs", json=run_request.model_dump(), headers=headers
        )
        if transport_status is not None:
            return templates.TemplateResponse(
                request, "error.html", {"message": _UNAVAILABLE_ERROR}, status_code=transport_status
            )
        if response.status_code in (502, 504):
            return templates.TemplateResponse(
                request,
                "error.html",
                {"message": _UNAVAILABLE_ERROR},
                status_code=response.status_code,
            )
        if response.status_code == 422:
            return templates.TemplateResponse(
                request,
                "run_new.html",
                {"error": _extract_detail(response), "values": values},
                status_code=422,
            )

        run = RunResponse(**response.json())

    return RedirectResponse(url=f"/runs/{run.id}", status_code=303)


@router.get("/runs/{run_id}")
def run_detail(
    request: Request,
    run_id: str,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
):
    with httpx.Client(base_url=base_url) as client:
        detail_response, transport_status = _call_downstream(
            client.get, f"/runs/{run_id}", headers=headers
        )
        if transport_status is not None:
            return templates.TemplateResponse(
                request, "error.html", {"message": _UNAVAILABLE_ERROR}, status_code=transport_status
            )
        if detail_response.status_code in (502, 504):
            return templates.TemplateResponse(
                request,
                "error.html",
                {"message": _UNAVAILABLE_ERROR},
                status_code=detail_response.status_code,
            )
        if detail_response.status_code == 404:
            return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

        run = RunDetailResponse(**detail_response.json())

        splits_response, splits_transport_status = _call_downstream(
            client.get, f"/runs/{run_id}/splits", headers=headers
        )
        if splits_transport_status is not None:
            return templates.TemplateResponse(
                request,
                "error.html",
                {"message": _UNAVAILABLE_ERROR},
                status_code=splits_transport_status,
            )
        if splits_response.status_code in (502, 504):
            return templates.TemplateResponse(
                request,
                "error.html",
                {"message": _UNAVAILABLE_ERROR},
                status_code=splits_response.status_code,
            )
        splits = (
            [SplitResultResponse(**item) for item in splits_response.json()]
            if splits_response.status_code == 200
            else []
        )

    return templates.TemplateResponse(
        request, "run_detail.html", {"run": run, "splits": splits}
    )
