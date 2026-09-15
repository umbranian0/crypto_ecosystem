"""`POST /runs` (VS-006): the service's literal trigger condition.

`RunRequest`/`RunResponse`/`RunDetailResponse` are imported from
`naive_first_common.contracts` (ARCH-003) -- this router is the canonical
source these shapes were copied from, and now imports the shared definition
like `gateway-api`'s router does, so there is exactly one definition instead
of two hand-synced copies.

Single responsibility: adapt an HTTP request into exactly one call to
`naive_first_engine.protocol.run_validation_protocol` (imported and invoked
as-is -- no wrapping/subclassing/reordering, per this ticket's Review
acceptance criteria) and persist its output via VS-003/004's repositories.
No split/baseline/metric/DM-test logic is reimplemented here.

Handler flow is fixed (VS-006 Design section, must match exactly):
validate request -> `DatasetSource.load` -> build `ValidationConfig` ->
`create_run` -> `run_validation_protocol` -> map each `SplitResult` to a
`split_results` row (model_*=naive_last, naive0_*=naive0, dm_*=naive_last's
DMResult -- app.models' module docstring) and persist via `add_splits` ->
`update_run_status("completed")` -> return `{id, status}`.

Synchronous by design (VS-006 Design section): this interim implementation
runs the whole protocol within the request/response cycle, so the initial
status `ValidationRunRepository.create_run` persists (`"pending"` -- VS-003/
VS-004's `create_run` signature takes no `status` argument, so this handler
cannot request `"running"` literally; `"pending"` is that same in-flight
placeholder in practice here) is immediately followed by `update_run_status`
to `"completed"` before the response is returned -- no Prefect/worker
orchestration exists yet (backlog AC5). A future async-execution ticket would
split `create_run` and the protocol call + `update_run_status` across a
request and a background job.

`dataset_id`: not part of a `datasets` registry (no such table exists in this
sprint's schema -- see solution-design.md section 4's `datasets` table, which
`validation-service` does not own or query). Passed through explicitly on the
request body; `tenant_id` is no longer a body field (VS-010) -- it is resolved
via `Depends(get_tenant_context)` from `naive_first_common` instead.

VS-012: `run_validation_protocol` and the split-mapping/`add_splits`
persistence that depends on its output are wrapped in a `try`/`except
Exception`, whose run row is created (via the local `_persist_new_run`
helper) immediately before that `try`, so a `run.id` always exists to attach
a `"failed"` status to. On any exception, the handler delegates to the local
`_fail_run` helper (UAT-006), which persists `status="failed"` with a
guaranteed non-empty, non-numeric `failure_reason` (never a bare
`str(exc)` -- see `_fail_run`'s own docstring for why a raw exception
string is not trustworthy on its own) via `update_run_status`, and returns
immediately from inside the `except` block with a `201` (the HTTP
request was handled correctly -- a run that fails is a completed *request*,
just an unsuccessful *run*; a bare `500` would suggest the service itself
malfunctioned). That `return` is what makes
`event_publisher.publish("run.completed", ...)` structurally unreachable on
failure: it sits after the whole `try`/`except` statement, so the only way
to reach it is for the `try` block to finish without raising -- there is no
`finally`, no fallthrough, nothing that could route a caught exception back
into it.

RSS-004: `DatasetSource.load` itself is no longer inside that `try` -- it now
runs first, in its own `try`/`except`, *before* any run row exists at all.
A load failure there creates the run row (via the same `_persist_new_run`
helper) and immediately marks it `"failed"`, preserving VS-012's exact
`"failed"`/`201` outward contract, just with the run row created one step
later than before this ticket. Once `series` loads successfully, the RSS-004
split-count guardrail (`MAX_SPLIT_COUNT`, see that constant's own comment)
calls `generate_splits` directly on `series.index` with the same arguments
`run_validation_protocol` uses internally and rejects with a `422` --
creating no run row and calling `run_validation_protocol` zero times -- if
the real computed split count would exceed the cap. Only once both the load
succeeds and the guardrail passes does the pre-existing `_persist_new_run` +
`try`/`except` flow described above run, reusing the already-loaded `series`
rather than loading it a second time.

`GET /runs/{id}` (VS-007): tenant is resolved the same way as `POST /runs`
(VS-010) -- via `Depends(get_tenant_context)`, not a query parameter. Tenant
isolation is load-bearing
(solution-design.md section 1 principle 3): `ValidationRunRepository.get_run`
(VS-004) already returns `None` for both "run doesn't exist" and "run belongs
to a different tenant" -- this handler translates `None` into a single `404`
for both cases, with no branch that would distinguish them (a `403`, or any
differently-shaped response for the cross-tenant case, would itself leak that
the run exists).

`GET /runs` (VS-022): tenant-scoped, paginated list of this tenant's runs,
closing `DASH-005-GAP` so `dashboard-web`'s runs-list page has something to
call. Tenant resolution is the same `Depends(get_tenant_context)` seam as the
other two handlers -- no bypass, no query-param tenant id. `limit`/`offset`
are validated by FastAPI's own `Query(...)` constraints (`ge=1, le=100` for
`limit`, `ge=0` for `offset`), so an out-of-range value never reaches this
function body -- it is rejected as a `422` before `ValidationRunRepository`
is touched at all, the same "validate before touching the repository"
precedent `POST /runs`' field constraints already established.
`ValidationRunRepository.list_runs` (not this handler) is responsible for the
`created_at` descending ordering, mirroring `get_splits`'s
"ordering is the repository's job" precedent (VS-003 Design section). An
empty tenant returns `200` with an empty `items` list, never a `404` -- an
empty list is a valid, successful answer to "what are this tenant's runs",
not an error.

VS-017: `POST /runs` optionally accepts `client_prediction_reference`
(same `DatasetSource`-compatible shape as `dataset_reference`). When present,
the handler loads it via the same `DatasetSourceDep` seam (no second
dataset-loading mechanism), wraps the resulting series in
`app.client_baseline.ClientPredictionBaseline` (a Strategy implementation of
`naive_first_engine.baselines.Baseline`), and passes it as
`ValidationConfig.extra_baselines=[...]` -- a third, strictly additive entry.
The two mandatory naive baselines (Naive0/NaiveLast) are never conditional on
this: `run_validation_protocol` always computes them the same way regardless
of `extra_baselines`'s contents (VS-019; `tests/test_naive_baselines_mandatory.py`
proves this structurally). When `client_prediction_reference` is absent (the
default), behavior is byte-identical to before this ticket (`extra_baselines=[]`,
`client_baseline_results=None` on every persisted split).
"""

from __future__ import annotations

import dataclasses
from datetime import datetime
from uuid import uuid4

from fastapi import APIRouter, Depends, HTTPException, Query
from pydantic import BaseModel

from naive_first_common import TenantContext, get_tenant_context
from naive_first_common.contracts import (
    RunDetailResponse,
    RunRequest,
    RunResponse,
    RunSummaryResponse,
)
from naive_first_engine.protocol import (
    NAIVE0_KEY,
    NAIVE_LAST_KEY,
    ValidationConfig,
    run_validation_protocol,
)
from naive_first_engine.splitting import generate_splits

from app.client_baseline import ClientPredictionBaseline
from app.dataset_source import DatasetSourceError
from app.dependencies.repositories import (
    ConnectorStatusCheckerDep,
    DatasetSourceDep,
    EventPublisherDep,
    FeatureDatasetAssemblerDep,
    SplitPointRepositoryDep,
    SplitResultRepositoryDep,
    ValidationRunRepositoryDep,
)
from app.feature_dataset import FeatureDatasetError
from app.level_detection import (
    LAG1_AUTOCORR_THRESHOLD,
    MEAN_OVER_STD_THRESHOLD,
    detect_price_level_series,
)
from app.repositories.interfaces import SplitPointRecord, SplitResultRecord

router = APIRouter()

# RSS-004 (docs/product/backlog-run-submission-safety.md OQ-1/OQ-2): a real
# incident (see that backlog entry and RSS-004's ticket Analysis section)
# measured ~78 splits/second on this hardware -- at that rate 500 splits take
# ~6.4s. This cap is deliberately far below what that single measurement
# would justify as a tighter number: it is a conservative-by-design safety
# margin against unbounded synchronous request duration, not a
# performance-tuned ceiling derived from a benchmark suite.
MAX_SPLIT_COUNT = 500


def _fail_run(
    run_repository,
    tenant: TenantContext,
    run,
    exc: Exception,
) -> RunResponse:
    """UAT-006: single failure-persistence path, reused by all three
    `except Exception as exc` blocks below (dataset load, feature
    assembly, protocol execution/split persistence) -- previously each
    block inlined its own `failure_reason=str(exc)` call (extract-on-
    second-duplication, implementation-plan.md section 9).

    **Root cause traced (UAT-006 Analysis)**: `str(exc)` alone is not
    reliably human-readable -- the concrete, reproducible failure shape
    this ticket was filed against is any exception whose `str()` collapses
    to a bare number (the textbook example: `str(KeyError(0)) == "0"`,
    since `BaseException.__str__` for a single-arg exception just returns
    `str(args[0])`, with no surrounding context). No first-party raise in
    this module, `naive_first_engine`, or `naive_first_common` was found
    to construct such an exception directly (every `DatasetSourceError`/
    `FeatureDatasetError`/`ValueError` raised in this codebase already
    embeds a descriptive f-string) -- the live incident this ticket
    responds to is therefore a genuine but not-locally-reproducible
    exception (e.g. a KeyError surfacing from a third-party/stdlib code
    path this handler calls into, such as pandas/numpy internals or a
    downstream HTTP client) whose message happens to be exactly this
    int-sentinel shape. Fixing this *at its source* means never trusting
    `str(exc)` to already be descriptive: every failure is wrapped with
    fixed, human-authored context (what failed), and any message that is
    empty or looks like a bare number (this exact "0" signature, or any
    other digits-only message from the same exception family) is replaced
    outright with a fixed, descriptive fallback that still names the
    exception's type and the run id for support follow-up -- not silently
    re-surfaced as a lone digit.
    """
    try:
        raw_reason = str(exc).strip()
    except Exception:
        # Blanket safety net (Implementation AC2): a `__str__` that itself
        # raises is exactly the "never-str()-able exception" case -- never
        # let that propagate out of failure handling.
        raw_reason = ""

    if not raw_reason or raw_reason.lstrip("-").isdigit():
        failure_reason = (
            f"Validation run failed with an unspecified internal error "
            f"({type(exc).__name__}). No further detail was available from "
            f"the underlying exception; contact support with run id "
            f"{run.id} if this persists."
        )
    else:
        failure_reason = f"Validation run failed: {raw_reason}"

    run_repository.update_run_status(
        tenant.tenant_id, run.id, status="failed", failure_reason=failure_reason
    )
    return RunResponse(id=run.id, status="failed")


def _persist_new_run(
    run_repository,
    tenant: TenantContext,
    request: RunRequest,
    warnings: list[str],
    feature_lineage: list[dict] | None = None,
):
    return run_repository.create_run(
        tenant_id=tenant.tenant_id,
        dataset_id=request.dataset_id,
        horizon=request.horizon,
        purge_gap_hours=request.purge_gap_hours,
        split_config={
            "train_window": request.train_window,
            "test_window": request.test_window,
            "step": request.step,
        },
        warnings=warnings,
        feature_lineage=feature_lineage if feature_lineage is not None else [],
        label=request.label,
    )


def _json_safe_float(value: float) -> float | None:
    """`client_baseline_results` is persisted as a Postgres `JSON` column
    (0003_add_client_baseline_results.py), and Postgres's `json`/`jsonb`
    types reject the literal `NaN`/`Infinity` tokens Python's default JSON
    serialization emits for `float("nan")`/`float("inf")` -- unlike this
    table's existing flat `dm_statistic`/`dm_pvalue` float8 columns, which
    store `NaN` natively without issue (real, found live: a single-test-point
    split's zero-variance DM statistic is `NaN`, and persisting it inside the
    nested `client_baseline_results` JSON blob raised
    `psycopg.errors.InvalidTextRepresentation: Token "NaN" is invalid`).
    Mapped to `None` here, the same "unrepresentable -> null, not a crash"
    convention `RedisStreamsEventPublisher`'s own `None -> ""` field handling
    already uses in `events.py`, applied to the JSON-incompatible-float case
    instead of the missing-value case.
    """
    import math

    if value is None or math.isnan(value) or math.isinf(value):
        return None
    return value


class RunListResponse(BaseModel):
    """Response envelope for `GET /runs` (VS-022 Design section): `items` is
    the current page (`RunSummaryResponse`, imported from
    `naive_first_common.contracts`, never redefined here); `limit`/`offset`
    echo back the resolved query params; `total` is a real, unpaginated count
    of this tenant's runs (`ValidationRunRepository.count_runs`), not omitted.
    This envelope shape is local to this router, not a shared contract --
    unlike `RunSummaryResponse`, GW-016's own proxy endpoint defines its own
    envelope if/when it needs one.
    """

    items: list[RunSummaryResponse]
    limit: int
    offset: int
    total: int


@router.post("/runs", response_model=RunResponse, status_code=201)
def create_run(
    request: RunRequest,
    dataset_source: DatasetSourceDep,
    run_repository: ValidationRunRepositoryDep,
    split_repository: SplitResultRepositoryDep,
    split_point_repository: SplitPointRepositoryDep,
    event_publisher: EventPublisherDep,
    feature_dataset_assembler: FeatureDatasetAssemblerDep,
    connector_status_checker: ConnectorStatusCheckerDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> RunResponse:
    # VS-017: config.extra_baselines only ever gains a third, optional entry
    # here -- the two mandatory naive baselines (NAIVE0_KEY/NAIVE_LAST_KEY)
    # are always computed by run_validation_protocol itself, unconditionally,
    # regardless of this list's contents (see naive_first_engine.protocol).
    # When request.client_prediction_reference is None (the default), this
    # is extra_baselines=[], byte-identical to before this ticket -- the
    # client series is loaded, if at all, inside the try block below,
    # alongside the primary dataset load it mirrors.
    config = ValidationConfig(
        train_window=request.train_window,
        test_window=request.test_window,
        step=request.step,
        purge_gap=request.purge_gap_hours,
        horizon=request.horizon,
    )

    # RSS-004: the dataset is loaded *before* any run row exists (unlike
    # VS-012's original ordering), so the RSS-004 guardrail below can compute
    # a real split count from the real index before deciding whether a run
    # row -- or any protocol computation -- should happen at all. A load
    # failure still needs a run.id to attach a "failed" status to (VS-012's
    # existing, tested contract), so this branch creates the run row itself,
    # one step later than before, then immediately marks it failed.
    try:
        loaded = dataset_source.load(request.dataset_reference)
    except Exception as exc:
        # DH-001: no LoadedSeries exists yet at this point (the exception
        # fired before unpacking), so this branch's warnings are unchanged
        # from today -- empty.
        run = _persist_new_run(run_repository, tenant, request, warnings=[])
        return _fail_run(run_repository, tenant, run, exc)

    series = loaded.series
    warnings = loaded.warnings

    # VS-030/ADR-0009: alignment must run to completion -- producing the
    # final index/feature_dataframe -- strictly before generate_splits/
    # RSS-004's guardrail below is invoked, and the reassigned `series` used
    # for every downstream guardrail and for run_validation_protocol is the
    # post-alignment series (never a superset of the original target index).
    # A defense-in-depth re-check of missing_timestamp_policy's presence --
    # RunRequest's own model_validator (naive_first_common.contracts) is the
    # primary enforcement point and already rejected this with 422 before
    # this handler body ever ran if it were missing.
    feature_lineage: list[dict] = []
    if request.feature_references:
        if request.missing_timestamp_policy is None:
            raise HTTPException(
                status_code=422,
                detail="missing_timestamp_policy is required whenever feature_references "
                "is non-empty",
            )
        try:
            assembled = feature_dataset_assembler.assemble(
                target_index=series.index,
                feature_references=request.feature_references,
                missing_timestamp_policy=request.missing_timestamp_policy,
                dataset_source=dataset_source,
                connector_status_checker=connector_status_checker,
            )
        except Exception as exc:
            run = _persist_new_run(run_repository, tenant, request, warnings=warnings)
            return _fail_run(run_repository, tenant, run, exc)

        series = series.loc[assembled.index]
        warnings = warnings + assembled.warnings
        feature_lineage = assembled.lineage

    # RSS-004 guardrail: call generate_splits directly (the same function
    # run_validation_protocol calls internally, same arguments) so this
    # check can never disagree with the real computation -- no independently
    # reimplemented split-count formula. This runs before any run row is
    # created and before run_validation_protocol is ever invoked, so a
    # rejected request persists nothing and spends no CPU on baselines/
    # metrics/DM-test.
    split_count = len(
        generate_splits(
            series.index,
            config.train_window,
            config.test_window,
            config.step,
            purge_gap=config.purge_gap,
        )
    )
    # DH-005: same "compute once, branch twice" shape RSS-004 already
    # established for the over-cap case -- reuses the already-computed
    # split_count and series length, no second generate_splits call and no
    # independently reimplemented split-count formula.
    if split_count == 0:
        required = config.train_window + config.purge_gap + config.test_window
        raise HTTPException(
            status_code=422,
            detail=(
                f"This configuration produces no splits. This dataset has "
                f"{len(series)} rows; train_window ({config.train_window}) + "
                f"purge_gap ({config.purge_gap}) + test_window "
                f"({config.test_window}) = {required} exceeds that, so 0 "
                "splits would result. Reduce train_window/test_window or "
                "choose a dataset with more rows."
            ),
        )
    if split_count > MAX_SPLIT_COUNT:
        raise HTTPException(
            status_code=422,
            detail=(
                f"This request would compute {split_count} splits, exceeding "
                f"the maximum of {MAX_SPLIT_COUNT} splits allowed per run. "
                "Reduce the split count by increasing 'step', narrowing the "
                "dataset's date range, and/or reducing 'train_window'/"
                "'test_window'."
            ),
        )

    # MR-001: price-level guardrail -- reuses the already-loaded `series`
    # (no second dataset load), runs after the DH-005 zero-split check and
    # before any run row is created / run_validation_protocol is invoked,
    # same "no run row, zero engine calls on rejection" property RSS-004/
    # DH-005 already have. See app.level_detection's module docstring for
    # the heuristic and thresholds; no auto-transform is performed -- a
    # flagged series is rejected, not silently differenced into returns.
    level_result = detect_price_level_series(series)
    if level_result.is_price_level:
        raise HTTPException(
            status_code=422,
            detail=(
                "This series looks like a raw price/metric level, not a "
                "returns series (lag-1 autocorrelation "
                f"{level_result.lag1_autocorr:.4f} exceeds "
                f"{LAG1_AUTOCORR_THRESHOLD}, and abs(mean)/std "
                f"{level_result.mean_over_std:.4f} exceeds "
                f"{MEAN_OVER_STD_THRESHOLD}). Naive0 is nonsensically wrong "
                "by construction on a raw level, producing a misleadingly "
                "favorable verdict. Resubmit a returns-based series -- e.g. "
                "a different 'field', or a pre-differenced dataset."
            ),
        )

    # Created before the try below (VS-012) so a run.id always exists to
    # attach a "failed" status to, even if something inside the try raises.
    # DH-001: the primary dataset load's own disclosed warnings (e.g. a
    # reordering-on-load notice) are persisted on the run row itself.
    run = _persist_new_run(
        run_repository, tenant, request, warnings=warnings, feature_lineage=feature_lineage
    )

    try:
        # VS-017: an optional third baseline, loaded the same way as the
        # primary dataset (same DatasetSourceDep, no second loading
        # mechanism) and passed as config.extra_baselines. This is the ONLY
        # place extra_baselines is ever set to something other than [] --
        # when request.client_prediction_reference is None, run_config below
        # is `config` itself, unchanged, so this whole branch is provably
        # inert for every pre-ticket request shape.
        run_config = config
        client_baseline_key: str | None = None
        if request.client_prediction_reference is not None:
            # DH-001: this optional third load's own warnings (if any) are
            # not currently persisted anywhere -- the ticket's binding scope
            # is the primary dataset_reference load only (Design section);
            # not extended to this second call site here.
            client_series = dataset_source.load(request.client_prediction_reference).series
            client_baseline = ClientPredictionBaseline(client_series)
            client_baseline_key = type(client_baseline).__name__
            run_config = dataclasses.replace(config, extra_baselines=[client_baseline])

        results = run_validation_protocol(series, run_config)

        # VS-031: minted once per run, before this run's created_at is
        # persisted -- see _persist_new_run above, run.created_at is already
        # the value split_points.created_at must copy (Design section: "not
        # datetime.utcnow() recomputed per row").
        run_created_at = run.created_at

        split_records = []
        split_point_records: list[SplitPointRecord] = []
        for split in results:
            model = split.baseline_results[NAIVE_LAST_KEY]
            naive0 = split.baseline_results[NAIVE0_KEY]
            dm_result = model.dm_result

            # VS-031: raw per-point predicted/actual values, captured as a
            # side effect of the already-computed BaselineResult.predictions
            # Series (naive_first_engine.report_schema) -- never a second
            # .predict() call. `actual` comes from the same input `series`
            # this run's protocol call already consumed (predictions.index
            # is a subset of series.index, the split's test window).
            points_by_baseline_key = {
                NAIVE_LAST_KEY: model,
                NAIVE0_KEY: naive0,
            }
            if client_baseline_key is not None:
                points_by_baseline_key[client_baseline_key] = split.baseline_results[
                    client_baseline_key
                ]
            for baseline_key, baseline_result in points_by_baseline_key.items():
                predictions = baseline_result.predictions
                if predictions is None:
                    continue
                actual_values = series.loc[predictions.index]
                for timestamp, predicted_value, actual_value in zip(
                    predictions.index, predictions.to_numpy(), actual_values.to_numpy()
                ):
                    split_point_records.append(
                        SplitPointRecord(
                            id=uuid4().hex,
                            run_id=run.id,
                            tenant_id=tenant.tenant_id,
                            split_index=split.split_index,
                            baseline_key=baseline_key,
                            timestamp=timestamp,
                            predicted=float(predicted_value),
                            actual=float(actual_value),
                            created_at=run_created_at,
                        )
                    )

            client_baseline_results = None
            if client_baseline_key is not None:
                client_result = split.baseline_results[client_baseline_key]
                client_dm = client_result.dm_result
                client_baseline_results = {
                    "key": client_baseline_key,
                    "metrics": {
                        "mae": _json_safe_float(client_result.metrics.mae),
                        "rmse": _json_safe_float(client_result.metrics.rmse),
                        "smape": _json_safe_float(client_result.metrics.smape),
                        "mase": _json_safe_float(client_result.metrics.mase),
                        "da": _json_safe_float(client_result.metrics.da),
                        "f1": _json_safe_float(client_result.metrics.f1),
                        "oos_r2": _json_safe_float(client_result.metrics.oos_r2),
                    },
                    "dm_statistic": _json_safe_float(client_dm.statistic),
                    "dm_pvalue": _json_safe_float(client_dm.p_value),
                    "dm_verdict": client_dm.verdict,
                }

            split_records.append(
                SplitResultRecord(
                    id=uuid4().hex,
                    run_id=run.id,
                    tenant_id=tenant.tenant_id,
                    split_index=split.split_index,
                    train_start=split.boundaries.train_start,
                    train_end=split.boundaries.train_end,
                    purge_start=split.boundaries.purge_start,
                    purge_end=split.boundaries.purge_end,
                    test_start=split.boundaries.test_start,
                    test_end=split.boundaries.test_end,
                    model_mae=model.metrics.mae,
                    model_rmse=model.metrics.rmse,
                    model_smape=model.metrics.smape,
                    model_mase=model.metrics.mase,
                    model_da=model.metrics.da,
                    model_f1=model.metrics.f1,
                    model_oos_r2=model.metrics.oos_r2,
                    naive0_mae=naive0.metrics.mae,
                    naive0_rmse=naive0.metrics.rmse,
                    naive0_smape=naive0.metrics.smape,
                    naive0_mase=naive0.metrics.mase,
                    naive0_da=naive0.metrics.da,
                    naive0_f1=naive0.metrics.f1,
                    naive0_oos_r2=naive0.metrics.oos_r2,
                    dm_statistic=dm_result.statistic,
                    dm_pvalue=dm_result.p_value,
                    dm_verdict=dm_result.verdict,
                    client_baseline_results=client_baseline_results,
                )
            )

        split_repository.add_splits(tenant.tenant_id, run.id, split_records)
        split_point_repository.add_points(tenant.tenant_id, run.id, split_point_records)
    except Exception as exc:
        # Returning here ends the request. `event_publisher.publish` below
        # is unreachable from this branch by construction -- it sits after
        # this entire try/except statement, with no finally/fallthrough
        # connecting the two.
        return _fail_run(run_repository, tenant, run, exc)

    completed_at = datetime.utcnow()
    run_repository.update_run_status(
        tenant.tenant_id, run.id, status="completed", completed_at=completed_at
    )

    event_publisher.publish(
        "run.completed",
        {
            "run_id": run.id,
            "tenant_id": tenant.tenant_id,
            "status": "completed",
            "completed_at": completed_at.isoformat(),
        },
    )

    return RunResponse(id=run.id, status="completed")


@router.get("/runs", response_model=RunListResponse)
def list_runs(
    run_repository: ValidationRunRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
) -> RunListResponse:
    runs = run_repository.list_runs(tenant.tenant_id, limit, offset)
    total = run_repository.count_runs(tenant.tenant_id)

    return RunListResponse(
        items=[
            RunSummaryResponse(
                id=run.id,
                dataset_id=run.dataset_id,
                horizon=run.horizon,
                status=run.status,
                created_at=run.created_at,
                completed_at=run.completed_at,
                label=run.label,
            )
            for run in runs
        ],
        limit=limit,
        offset=offset,
        total=total,
    )


@router.get("/runs/{run_id}", response_model=RunDetailResponse)
def get_run(
    run_id: str,
    run_repository: ValidationRunRepositoryDep,
    split_repository: SplitResultRepositoryDep,
    tenant: TenantContext = Depends(get_tenant_context),
) -> RunDetailResponse:
    # `get_run` already returns None for both "doesn't exist" and "wrong
    # tenant" (VS-004) -- both collapse into this single 404, no branch
    # distinguishes them (VS-007 Design section, AC2).
    run = run_repository.get_run(tenant.tenant_id, run_id)
    if run is None:
        raise HTTPException(status_code=404, detail="run not found")

    # VS-029: has_client_model is derived from the same per-split
    # client_baseline_results signal VS-017 already established (splits.py's
    # _client_baseline_response condition) -- any(), not "check the first
    # split only", the honest non-assumption-dependent way to derive a
    # run-level fact from per-split data. A run with zero splits (pending/
    # failed status) is False -- no splits to derive True from.
    splits = split_repository.get_splits(tenant.tenant_id, run_id)
    has_client_model = any(split.client_baseline_results is not None for split in splits)

    return RunDetailResponse(
        id=run.id,
        tenant_id=run.tenant_id,
        dataset_id=run.dataset_id,
        horizon=run.horizon,
        purge_gap_hours=run.purge_gap_hours,
        split_config=run.split_config,
        status=run.status,
        created_at=run.created_at,
        completed_at=run.completed_at,
        failure_reason=run.failure_reason,
        warnings=run.warnings,
        has_client_model=has_client_model,
        feature_lineage=run.feature_lineage,
        # VS-030: derived, single source of truth (run.feature_lineage) --
        # same precedent VS-029 established for has_client_model.
        has_multimodal_features=bool(run.feature_lineage),
        label=run.label,
    )


@router.get("/runs/{run_id}/features")
def get_run_features(
    run_id: str,
    run_repository: ValidationRunRepositoryDep,
    dataset_source: DatasetSourceDep,
    feature_dataset_assembler: FeatureDatasetAssemblerDep,
    connector_status_checker: ConnectorStatusCheckerDep,
    tenant: TenantContext = Depends(get_tenant_context),
    missing_timestamp_policy: str = Query(default="drop_row"),
) -> dict:
    """MR-007: read-only re-export of the multi-column feature table
    `FeatureDatasetAssembler.assemble` built for this run, keyed by
    `run_id`. Thin HTTP adapter only -- reuses `FeatureDatasetAssembler`/
    `DatasetSource` exactly as `create_run` already does; no alignment or
    dispatch logic is reimplemented here (ADR-0008/ADR-0009 remain owned by
    `feature_dataset.py`/`dataset_source.py`).

    **Disclosed, binding limitation (MR-007 Analysis section -- a real,
    documented schema gap, not an oversight)**: `runs.missing_timestamp_policy`
    and the original `dataset_reference` dict `POST /runs` used are not
    persisted anywhere, so this route cannot literally replay the original
    `assemble()` call:

    - `missing_timestamp_policy` is accepted here as an optional query
      parameter, defaulting to the strictest policy (`"drop_row"`) when
      omitted. If the caller passes a different policy than the run's
      original, the returned table may legitimately have a different row
      count than the original run's own target index -- a known,
      documented limitation, not a bug.
    - The primary series is reloaded via
      `dataset_source.load({"source": run.dataset_id})` (the
      `IngestionServiceDatasetSource` shape) -- this only works for runs
      whose original `dataset_reference` was ingestion-service-backed with
      `source == dataset_id`. A run originally loaded via `inline`/`path`/
      `object_key` cannot be re-loaded this way; this route returns `422`
      naming that limitation explicitly rather than silently returning an
      empty/wrong table.
    - `feature_references` are reconstructed from `run.feature_lineage` as
      `{"source", "field"}` pairs -- `lag_hours` is dropped, since it is
      *derived* by `feature_dataset.py`'s `FEATURE_SOURCE_LAG_HOURS` table
      from `source`, not an input to `assemble()`.

    This is a first-cut, disclosed-limitation implementation (MR-007's own
    backlog framing) -- not a fully general feature-re-assembly API.
    """
    # Same single-404-for-both-cases pattern `get_run` already establishes
    # (VS-004/VS-007): "doesn't exist" and "wrong tenant" collapse into one
    # 404, and a run with no multimodal features (feature_lineage == [],
    # the same has_multimodal_features derivation get_run already uses)
    # collapses into the same 404 rather than a distinct empty response.
    run = run_repository.get_run(tenant.tenant_id, run_id)
    if run is None or not run.feature_lineage:
        raise HTTPException(status_code=404, detail="run not found")

    feature_references = [
        {"source": entry["source"], "field": entry["field"]} for entry in run.feature_lineage
    ]

    try:
        loaded = dataset_source.load({"source": run.dataset_id})
    except DatasetSourceError as exc:
        raise HTTPException(
            status_code=422,
            detail=(
                f"could not reload the primary series for run {run_id!r} via "
                f"dataset_source.load({{'source': {run.dataset_id!r}}}): {exc}. "
                "This route can only re-export features for runs whose original "
                "dataset_reference was ingestion-service-backed with "
                "source == dataset_id -- a run originally loaded via inline/path/"
                "object_key cannot be re-loaded this way (MR-007 disclosed "
                "limitation)."
            ),
        ) from exc

    try:
        assembled = feature_dataset_assembler.assemble(
            target_index=loaded.series.index,
            feature_references=feature_references,
            missing_timestamp_policy=missing_timestamp_policy,
            dataset_source=dataset_source,
            connector_status_checker=connector_status_checker,
        )
    except FeatureDatasetError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc

    # `pandas.DataFrame.to_dict(orient="split")` is the {"index", "columns",
    # "data"} shape MR-007's backlog entry itself proposes -- reused here
    # rather than hand-rolled; FastAPI's own jsonable_encoder already renders
    # the pandas.Timestamp index entries as ISO8601 strings.
    return assembled.feature_dataframe.to_dict(orient="split")
