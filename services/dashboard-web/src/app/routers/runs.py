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

DASH-108: a third `dataset_reference` mode, "Stored dataset" (`{"source":
..., "start": ..., "end": ..., "field": ...}`, per ADR-0005's continuous-
table semantics -- a dataset is a `{tenant, source}` table, so selecting one
means selecting a source plus an optional time-range slice, not a discrete
snapshot). Extends the same `if path / elif inline / elif source / else
error` chain `run_new_submit` already used for the first two modes -- not a
redesign, and the first two `elif` branches are untouched. `start`/`end`/
`field` are included in the constructed `dataset_reference` dict only when
non-blank (omitted, not sent as `None`/empty string), matching
`GET /ingestion/datasets/{source}/series`'s own optional-both-ends semantics
(ADR-0005, GW-020/INGEST-009). `run_new_form` (`GET /runs/new`) now also
calls gateway-api's `GET /ingestion/datasets` (GW-020) via the same
`_call_downstream` helper to populate this mode's source dropdown; a
transport failure or non-200 there degrades to an empty dataset list (the
same "no ingested datasets yet" empty state a real empty-history tenant
sees) rather than blocking the whole page, since the pre-existing path/
inline modes must stay usable regardless of this one endpoint's
availability.

DASH-005-01: `GET /runs` (this same file, per this ticket's own Design section
-- no second router module) calls gateway-api's real `GET /runs` (GW-016,
itself a pass-through proxy of validation-service's VS-022) and renders
`runs_list.html`, one row per run, in the server's own `created_at DESC`
order (no client-side re-sort). The response envelope is parsed as
`{"items": [...], "limit": ..., "offset": ..., "total": ...}`; each item is
validated via the shared `RunSummaryResponse` (imported from
`naive_first_common.contracts`, ARCH-003) -- `RunListResponse` itself is
*not* imported from there (it does not exist in that module; per
`services/gateway-api/README.md`'s own Contract section, it is that router's
own page/router-local envelope, mirrored here the same way rather than a
shared contract class). If the incoming request carries `limit`/`offset`
query params they are forwarded to gateway-api unmodified (no locally
invented defaults, no re-validation of gateway-api's/validation-service's own
bounds); a non-200 response (including a `422` for an out-of-range value,
forwarded generically the same way a transport failure is, since this list
page has no form to redisplay a field-specific error against) reuses the
same `_render_error_for_status` helper the `502`/`504` paths below use --
this is the third occurrence of that exact "render `error.html` with a fixed
message" branch across `run_new_submit`/`run_detail`/this route, so it is
extracted into a helper here rather than copy-pasted a third time
(implementation-plan.md section 9's "extract on second duplication" rule,
per this ticket's own DRY check note). Zero runs renders `runs_list.html`'s
own plain empty-state message, not an error.

DASH-111: `GET /datasets` (this same file, same "no second router module"
precedent DASH-005-01 set) lists all of a tenant's ingested datasets via the
same `GET /ingestion/datasets` call `run_new_form` (DASH-108) already makes.
`_fetch_ingestion_datasets` below is `run_new_form`'s original inline
fetch-and-degrade logic pulled out into one shared function both routes call
-- not two near-identical implementations of the same fetch (ticket's own DRY
check note). `run_new_form` also grew an optional `dataset_reference_source`
query param so this new page's "Submit a run" link
(`/runs/new?dataset_reference_source=<source>`) pre-selects that source in
the "Stored dataset" dropdown -- reusing the exact same `values.
dataset_reference_source == dataset.source` template comparison
`run_new_submit`'s error-redisplay path already relies on, not a second
selection mechanism. The "Trigger a crawl" link per row points at
`/monitoring` -- a forward-compatible placeholder only, since DASH-110 (the
ticket that would wire up an actual per-source crawl trigger from this page)
is not yet built; this ticket does not build that functionality itself.

RAV-002: `run_detail` now also passes `splits` through `app.charting`'s
`build_error_chart` (a pure function, no I/O) and hands the resulting
`ErrorChartData` to `run_detail.html` as `error_chart`, rendered by the new
`_error_chart.html` partial (per RAV-001's server-rendered-SVG decision,
docs/adr/0006-dashboard-web-charting-server-rendered-svg.md). No new
downstream call -- the same `GET /runs/{id}/splits` response this handler
already fetches is reused.

RAV-004: `run_detail` reads an optional `metric` query param (default
`"mae"`) and passes it through to `build_error_chart`. An unrecognized value
is not re-validated here a second time -- `build_error_chart` itself already
falls back to `"mae"` for any key not in `app.charting.METRIC_REGISTRY`, so
this route just forwards the raw query value rather than duplicating that
registry lookup (this is a display preference, not a form submission with a
422 path, per this ticket's Design section). `error_chart.metric` (the
resolved, possibly-fallen-back-to value `build_error_chart` returns) is what
`run_detail.html`'s selector control uses to mark the active option, not the
raw query param.

RAV-003: `run_detail` likewise passes the same `splits` list through
`app.charting`'s `build_dm_verdict_chart` and hands the resulting
`DmVerdictChartData` to `run_detail.html` as `dm_verdict_chart`, rendered by
`_dm_verdict_chart.html`. No new downstream call here either.

FHS-003: `run_detail` also builds `horizon_summary_rows` -- the same `splits`
list zipped with `app.charting.verdict_category_and_css_slug(split)` per
split -- and hands it to `run_detail.html` as `horizon_summary_rows`, rendered
by the new `_forecast_horizon_summary_panel.html` partial. Reuses the same
per-split None-DM-value rule `build_dm_verdict_chart` already established
(`UNDEFINED_VERDICT_CATEGORY`) rather than re-deriving it in the template. No
new downstream call.

FHS-002: `GET /runs/horizon-summary` (this same file, same "no second router
module" precedent DASH-005-01/DASH-111 set) presents a 7/15/30-day horizon
selector and filters the tenant's own `GET /runs` (the exact same call
`runs_list` above makes -- no new backend endpoint, per
`docs/adr/0007-forecast-horizon-summary-unit-and-scope.md`) client-side by
`run.horizon`. `_horizon_for_days` below converts the selector's `days` value
to `horizon` using the ADR's disclosed, hourly-only-for-now conversion
constants (`HOURS_PER_DAY`, `ASSUMED_SAMPLING_INTERVAL_HOURS`), named and
commented rather than inlined as a magic number. Registered before
`run_detail`'s `/runs/{run_id}` (a Starlette literal-segment route must
precede a same-position path-param route it would otherwise be shadowed by,
same ordering rule DASH-006's docstring above already states for
`/runs/new`). Reuses `_call_downstream`/`_render_error_for_status` -- no new
transport-failure handling. A `days` value with zero matching runs renders an
explicit empty state (never a silent empty table, never a fallback to a
different horizon), per the ADR's (c) decision.

FHS-004: `run_detail` also builds `shareable_summary_text` via the new
`build_shareable_summary_text` (pure function, no I/O, below) -- the same
already-fetched `run`/`splits` this handler already has, rendered by the new
`_shareable_summary.html` partial as a readonly `<textarea>` plus a "Copy"
button. No new downstream call, no persistence of the generated text.

RAV-009: `GET /runs/trend` (this same file, same "no second router module"
precedent DASH-005-01/DASH-111/FHS-002 set) -- see this ticket's own Analysis
section: no new backend endpoint is introduced, only client-side aggregation
of the two already-existing `GET /runs` and `GET /runs/{id}/splits` calls.
Registered before `run_detail`'s `/runs/{run_id}` (same literal-segment-
before-path-param ordering rule `/runs/new`/`/runs/horizon-summary` already
follow). First call is the exact same `GET /runs` `runs_list`/
`runs_horizon_summary` already make, grouped client-side by
`(dataset_id, horizon)` for the selector -- no group/metric selected yet
renders only the selector, mirroring `runs_horizon_summary`'s own
no-`days`-yet behavior. Once a group (`dataset_id`+`horizon`) and a metric
are selected, only that group's `completed` runs (`running`/`failed` runs
skipped -- a non-completed run is not evidence of anything yet, the same
reasoning `runs_horizon_summary` already applies) each get their own
`GET /runs/{id}/splits` call, and the resulting `(run, splits)` pairs are
passed to `app.charting.build_trend_chart`. Framed throughout as "how this
model configuration's validation results have varied across completed
runs" -- never "trend" language implying a forecast of a future run's
outcome (this ticket's Design section, CLAUDE.md's positioning constraint).

RAV-010: the same `(run, splits)` pairs computed above (no second
`GET /runs/{id}/splits` call) are also passed to
`app.charting.compute_consistency_indicator`, which counts how many of those
completed runs had a majority "better"-than-Naive0 verdict across their own
splits. Rendered next to the trend chart as "beat Naive0 in N of M completed
runs" -- a purely descriptive count of already-computed DM-test outcomes,
never a probability or recommendation. Zero evaluable runs render a plain
"no completed runs matched this selection" message, never a fabricated
"0 of 0" ratio.
"""

from __future__ import annotations

import json

import httpx
from fastapi import APIRouter, Form, Request
from fastapi.responses import RedirectResponse
from naive_first_common.contracts import (
    DatasetSummaryResponse,
    RunDetailResponse,
    RunRequest,
    RunResponse,
    RunSummaryResponse,
    SplitResultResponse,
)
from pydantic import ValidationError

from app.charting import (
    DEFAULT_METRIC,
    METRIC_REGISTRY,
    build_dm_verdict_chart,
    build_error_chart,
    build_trend_chart,
    compute_consistency_indicator,
    verdict_category_and_css_slug,
)
from app.dependencies.downstream import DownstreamHeadersDep, GatewayApiUrlDep
from app.main import templates

router = APIRouter()

_UNAVAILABLE_ERROR = "results currently unavailable"
_MISSING_DATASET_REFERENCE_ERROR = (
    "Provide either a local file path, an inline payload, or a stored dataset "
    "for the dataset reference."
)
_INVALID_INLINE_JSON_ERROR = "Inline payload must be valid JSON."

# FHS-002 / docs/adr/0007-forecast-horizon-summary-unit-and-scope.md: `horizon`
# is a count of the dataset's own sampling steps, not a fixed time unit
# (ADR-0007 (a)). The one real price source today
# (`binance_price_btcusdt_1h`) samples hourly, so this feature's day-based
# selector hardcodes that assumption rather than doing a per-dataset lookup
# (explicitly flagged in the ADR as the thing to revisit if a non-hourly
# source is ever added -- YAGNI until then).
HOURS_PER_DAY = 24
ASSUMED_SAMPLING_INTERVAL_HOURS = 1

# The selector's only supported day values (ADR-0007 (b)) -> converted
# `horizon` values, for the one real hourly source today.
HORIZON_SUMMARY_DAY_OPTIONS = (7, 15, 30)

# FHS-004: ADR-0007's forward conversion (`_horizon_for_days`) reversed --
# only the three `horizon` values that conversion can actually produce
# (168/360/720, for the one real hourly source today) are given a day label;
# any other `horizon` shows the raw integer with no fabricated unit (the
# ADR's own "no silent generalization" rule).
_HORIZON_TO_DAY_LABEL = {168: "7 days", 360: "15 days", 720: "30 days"}

# FHS-004: the exact caveat sentence (backlog-mandated, verbatim) appended to
# every generated shareable summary -- the one string this ticket's test
# suite regression-proofs against silent weakening. The word "forecast" here
# is the single permitted usage (negated: "not a forecast of future
# performance") the banned-positioning-words scan must distinguish from any
# other, affirmative usage elsewhere in this module's templates.
CAVEAT_SENTENCE = (
    "This is a backtested validation result, not a forecast of future performance. "
    "Under this platform's own published research, no machine learning model has "
    "beaten a naive statistical baseline in a stable, significant way at any tested "
    "horizon -- treat any deviation shown here as unproven until independently "
    "reconfirmed."
)


def build_shareable_summary_text(
    run: RunDetailResponse, splits: list[SplitResultResponse]
) -> str:
    """FHS-004: a pure function (no I/O) producing a fixed-format plain-text
    block for the "copy summary" affordance -- dataset/run identifier, the
    horizon in the user-facing day unit (`_HORIZON_TO_DAY_LABEL`'s reverse of
    `_horizon_for_days`, falling back to the raw `horizon` value for an
    unrecognized value), naive-first baseline metric(s) and candidate-model
    metric(s) per split (the same per-split granularity FHS-003's panel
    already ships -- not a second aggregation), the DM verdict/p-value per
    split, and `CAVEAT_SENTENCE` verbatim appended at the end. Reuses the same
    already-fetched `run`/`splits` data FHS-003's panel renders -- no new
    downstream call.
    """
    horizon_label = _HORIZON_TO_DAY_LABEL.get(run.horizon, str(run.horizon))

    lines = [
        f"Validation run: {run.id}",
        f"Dataset: {run.dataset_id}",
        f"Horizon: {horizon_label}",
        "",
    ]

    for split in splits:
        lines.append(f"Split {split.split_index}:")
        lines.append(f"  Model MAE: {split.model_mae}  |  Naive0 MAE: {split.naive0_mae}")
        lines.append(f"  Model RMSE: {split.model_rmse}  |  Naive0 RMSE: {split.naive0_rmse}")
        lines.append(
            f"  Model sMAPE: {split.model_smape}  |  Naive0 sMAPE: {split.naive0_smape}"
        )
        lines.append(f"  Model MASE: {split.model_mase}  |  Naive0 MASE: {split.naive0_mase}")
        lines.append(f"  Model DA: {split.model_da}  |  Naive0 DA: {split.naive0_da}")
        lines.append(f"  Model F1: {split.model_f1}  |  Naive0 F1: {split.naive0_f1}")
        lines.append(
            f"  Model OOS R2: {split.model_oos_r2}  |  Naive0 OOS R2: {split.naive0_oos_r2}"
        )
        dm_pvalue = split.dm_pvalue if split.dm_pvalue is not None else "--"
        lines.append(f"  DM p-value: {dm_pvalue}  |  Benchmark comparison verdict: {split.dm_verdict}")
        lines.append("")

    lines.append(CAVEAT_SENTENCE)

    return "\n".join(lines)


def _horizon_for_days(days: int) -> int:
    """ADR-0007's `horizon_for(days, source_sampling_interval_hours)`
    conversion, hardcoded to the one real hourly source today
    (`ASSUMED_SAMPLING_INTERVAL_HOURS = 1`) -- resolves 7/15/30 days to
    horizon 168/360/720.
    """
    return days * HOURS_PER_DAY // ASSUMED_SAMPLING_INTERVAL_HOURS


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


def _fetch_ingestion_datasets(
    client: httpx.Client, headers: dict[str, str]
) -> list[DatasetSummaryResponse]:
    """DASH-111: extracted from `run_new_form`'s (DASH-108) original inline
    fetch so both that route and the new `datasets_list` route below share one
    "call `GET /ingestion/datasets` and get the list of items back"
    implementation instead of two near-identical copies (ticket's own DRY
    check note). A transport failure or non-200 response degrades to an empty
    list -- the same "no ingested datasets yet" empty state a real
    empty-history tenant sees -- rather than raising, matching DASH-108's
    original design note.
    """
    response, transport_status = _call_downstream(
        client.get, "/ingestion/datasets", headers=headers
    )
    if transport_status is None and response.status_code == 200:
        return [DatasetSummaryResponse(**item) for item in response.json()["items"]]
    return []


def _render_error_for_status(request: Request, status_code: int):
    """Renders the shared `error.html` "results currently unavailable"
    failure page for a given status code -- either a translated
    transport-level failure's synthetic `502`/`504` (`_call_downstream`
    above), or a non-2xx status forwarded from gateway-api itself. Extracted
    here because this is the third occurrence of this exact branch across
    `run_new_submit`/`run_detail`/`runs_list` (DASH-005-01) -- past the
    "extract on second duplication" threshold (implementation-plan.md
    section 9), per this ticket's own DRY check note.
    """
    return templates.TemplateResponse(
        request, "error.html", {"message": _UNAVAILABLE_ERROR}, status_code=status_code
    )


@router.get("/runs")
def runs_list(
    request: Request,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
    limit: int | None = None,
    offset: int | None = None,
):
    """DASH-005-01: calls gateway-api's real `GET /runs` (GW-016) and renders
    one row per run, in the server's own `created_at DESC` order -- see this
    module's own docstring for the full DASH-005-01 note. `limit`/`offset`
    are forwarded unmodified only if the incoming request itself supplied
    them (no locally invented defaults); registered near the top of the
    router for readability, though its own path (no path param) does not
    collide with `/runs/new` or `/runs/{run_id}` either way.
    """
    params: dict[str, int] = {}
    if limit is not None:
        params["limit"] = limit
    if offset is not None:
        params["offset"] = offset

    with httpx.Client(base_url=base_url) as client:
        response, transport_status = _call_downstream(
            client.get, "/runs", headers=headers, params=params
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        body = response.json()
        runs = [RunSummaryResponse(**item) for item in body["items"]]

    return templates.TemplateResponse(request, "runs_list.html", {"runs": runs})


@router.get("/datasets")
def datasets_list(request: Request, headers: DownstreamHeadersDep, base_url: GatewayApiUrlDep):
    """DASH-111: lists all of a tenant's ingested datasets (source,
    earliest/latest timestamp, row_count) via `_fetch_ingestion_datasets`
    above -- the same shared fetch `run_new_form` (DASH-108) uses, not a
    second near-identical implementation. Renders `datasets.html`, which
    links each row into `run_new_form`'s "Stored dataset" mode (pre-selecting
    that source) and toward `/monitoring` as a forward-compatible crawl
    placeholder (DASH-110's own territory, not built here). Registered near
    `runs_list`/before `run_new_form` for readability; its own path does not
    collide with any `/runs/*` pattern either way.
    """
    with httpx.Client(base_url=base_url) as client:
        datasets = _fetch_ingestion_datasets(client, headers)

    return templates.TemplateResponse(request, "datasets.html", {"datasets": datasets})


@router.get("/runs/horizon-summary")
def runs_horizon_summary(
    request: Request,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
    days: int | None = None,
):
    """FHS-002: see this module's own docstring for the full note. `days` is
    unset on first render (shows only the selector, no locally invented
    default, matching `runs_list`'s own convention); when set, calls the
    exact same `GET /runs` `runs_list` calls and filters the parsed
    `RunSummaryResponse` list by `run.horizon == _horizon_for_days(days)` AND
    `run.status == "completed"` (a `running`/`failed` run at the matching
    horizon is not evidence of anything yet and must not appear on a page
    framed as backtested validation results), most recent first (the
    response already comes back `created_at DESC` per DASH-005-01 -- no
    client re-sort).
    """
    if days is None:
        return templates.TemplateResponse(
            request,
            "horizon_summary.html",
            {"days": None, "horizon": None, "runs": None},
        )

    horizon = _horizon_for_days(days)

    with httpx.Client(base_url=base_url) as client:
        response, transport_status = _call_downstream(client.get, "/runs", headers=headers)
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        body = response.json()
        all_runs = [RunSummaryResponse(**item) for item in body["items"]]

    matching_runs = [
        run for run in all_runs if run.horizon == horizon and run.status == "completed"
    ]

    return templates.TemplateResponse(
        request,
        "horizon_summary.html",
        {"days": days, "horizon": horizon, "runs": matching_runs},
    )


@router.get("/runs/new")
def run_new_form(
    request: Request,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
    dataset_reference_source: str = "",
):
    """DASH-006's original pure static render now also fetches gateway-api's
    `GET /ingestion/datasets` (GW-020, DASH-108) to populate the "Stored
    dataset" mode's source dropdown, via the shared `_fetch_ingestion_datasets`
    helper above (DASH-111 extracted it out of this function so `datasets_list`
    can reuse it too). A transport failure or non-200 response degrades to an
    empty dataset list -- rendered as the same "no ingested datasets yet"
    empty state a real empty-history tenant sees -- rather than blocking the
    whole page, since the pre-existing path/inline modes remain usable
    regardless of this one endpoint's availability.

    DASH-111: an optional `dataset_reference_source` query param (only ever
    set by `datasets_list`'s per-row "Submit a run" link) pre-selects that
    source in the dropdown by populating `values.dataset_reference_source`,
    the same template field `run_new_submit`'s own error-redisplay path
    already uses for this -- no second selection mechanism invented. A GET
    with no such param behaves exactly as before (`values` stays `None`).
    """
    with httpx.Client(base_url=base_url) as client:
        datasets = _fetch_ingestion_datasets(client, headers)

    values = (
        {"dataset_reference_source": dataset_reference_source}
        if dataset_reference_source.strip()
        else None
    )

    return templates.TemplateResponse(
        request, "run_new.html", {"datasets": datasets, "values": values}
    )


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
    dataset_reference_source: str = Form(""),
    dataset_reference_start: str = Form(""),
    dataset_reference_end: str = Form(""),
    dataset_reference_field: str = Form(""),
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
        "dataset_reference_source": dataset_reference_source,
        "dataset_reference_start": dataset_reference_start,
        "dataset_reference_end": dataset_reference_end,
        "dataset_reference_field": dataset_reference_field,
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
                {"error": _INVALID_INLINE_JSON_ERROR, "values": values, "datasets": []},
                status_code=422,
            )
    elif dataset_reference_source.strip():
        dataset_reference = {"source": dataset_reference_source.strip()}
        if dataset_reference_start.strip():
            dataset_reference["start"] = dataset_reference_start.strip()
        if dataset_reference_end.strip():
            dataset_reference["end"] = dataset_reference_end.strip()
        if dataset_reference_field.strip():
            dataset_reference["field"] = dataset_reference_field.strip()
    else:
        return templates.TemplateResponse(
            request,
            "run_new.html",
            {"error": _MISSING_DATASET_REFERENCE_ERROR, "values": values, "datasets": []},
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
            {"error": str(exc), "values": values, "datasets": []},
            status_code=422,
        )

    with httpx.Client(base_url=base_url) as client:
        response, transport_status = _call_downstream(
            client.post, "/runs", json=run_request.model_dump(), headers=headers
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code in (502, 504):
            return _render_error_for_status(request, response.status_code)
        if response.status_code == 422:
            return templates.TemplateResponse(
                request,
                "run_new.html",
                {"error": _extract_detail(response), "values": values, "datasets": []},
                status_code=422,
            )

        run = RunResponse(**response.json())

    return RedirectResponse(url=f"/runs/{run.id}", status_code=303)


@router.get("/runs/trend")
def runs_trend(
    request: Request,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
    dataset_id: str | None = None,
    horizon: int | None = None,
    metric: str = DEFAULT_METRIC,
):
    """RAV-009: see this module's own docstring for the full note. Grouping
    is client-side over the same `GET /runs` response every other route in
    this file already fetches -- no new backend endpoint (this ticket's
    Analysis section).
    """
    with httpx.Client(base_url=base_url) as client:
        response, transport_status = _call_downstream(client.get, "/runs", headers=headers)
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if response.status_code != 200:
            return _render_error_for_status(request, response.status_code)

        body = response.json()
        all_runs = [RunSummaryResponse(**item) for item in body["items"]]

        groups: dict[tuple[str, int], list[RunSummaryResponse]] = {}
        for run in all_runs:
            groups.setdefault((run.dataset_id, run.horizon), []).append(run)

        selected_group = (
            (dataset_id, horizon) if dataset_id is not None and horizon is not None else None
        )

        trend_chart = None
        consistency_indicator = None
        if selected_group is not None and selected_group in groups:
            completed_runs = [
                run for run in groups[selected_group] if run.status == "completed"
            ]
            runs_with_splits: list[tuple[RunSummaryResponse, list[SplitResultResponse]]] = []
            for run in completed_runs:
                splits_response, splits_transport_status = _call_downstream(
                    client.get, f"/runs/{run.id}/splits", headers=headers
                )
                if splits_transport_status is not None:
                    return _render_error_for_status(request, splits_transport_status)
                if splits_response.status_code in (502, 504):
                    return _render_error_for_status(request, splits_response.status_code)
                splits = (
                    [SplitResultResponse(**item) for item in splits_response.json()]
                    if splits_response.status_code == 200
                    else []
                )
                runs_with_splits.append((run, splits))

            trend_chart = build_trend_chart(runs_with_splits, metric=metric)
            # RAV-010: reuses the same already-fetched `runs_with_splits` --
            # no second `GET /runs/{id}/splits` call.
            consistency_indicator = compute_consistency_indicator(runs_with_splits)

    return templates.TemplateResponse(
        request,
        "runs_trend.html",
        {
            "groups": sorted(groups.keys()),
            "selected_group": selected_group,
            "metric_options": METRIC_REGISTRY,
            "trend_chart": trend_chart,
            "consistency_indicator": consistency_indicator,
        },
    )


@router.get("/runs/{run_id}")
def run_detail(
    request: Request,
    run_id: str,
    headers: DownstreamHeadersDep,
    base_url: GatewayApiUrlDep,
    metric: str = "mae",
):
    with httpx.Client(base_url=base_url) as client:
        detail_response, transport_status = _call_downstream(
            client.get, f"/runs/{run_id}", headers=headers
        )
        if transport_status is not None:
            return _render_error_for_status(request, transport_status)
        if detail_response.status_code in (502, 504):
            return _render_error_for_status(request, detail_response.status_code)
        if detail_response.status_code == 404:
            return templates.TemplateResponse(request, "not_found.html", {}, status_code=404)

        run = RunDetailResponse(**detail_response.json())

        splits_response, splits_transport_status = _call_downstream(
            client.get, f"/runs/{run_id}/splits", headers=headers
        )
        if splits_transport_status is not None:
            return _render_error_for_status(request, splits_transport_status)
        if splits_response.status_code in (502, 504):
            return _render_error_for_status(request, splits_response.status_code)
        splits = (
            [SplitResultResponse(**item) for item in splits_response.json()]
            if splits_response.status_code == 200
            else []
        )

    # FHS-003: per-split (category, css_slug) pairs for the new validation
    # summary panel -- reuses `app.charting.verdict_category_and_css_slug`
    # (itself a thin wrapper over `build_dm_verdict_chart`'s own per-split
    # category rule), so the None-DM "undefined for this split" rule is
    # derived once, not re-implemented in the template.
    horizon_summary_rows = [
        (split, *verdict_category_and_css_slug(split)) for split in splits
    ]

    # FHS-004: the "copy summary" affordance's plain-text block, built from
    # the same already-fetched run/splits data -- no new downstream call, no
    # persistence.
    shareable_summary_text = build_shareable_summary_text(run, splits)

    return templates.TemplateResponse(
        request,
        "run_detail.html",
        {
            "run": run,
            "splits": splits,
            "error_chart": build_error_chart(splits, metric=metric),
            "metric_options": METRIC_REGISTRY,
            "dm_verdict_chart": build_dm_verdict_chart(splits),
            "horizon_summary_rows": horizon_summary_rows,
            "shareable_summary_text": shareable_summary_text,
        },
    )
