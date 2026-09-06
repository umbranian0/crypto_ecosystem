"""Server-rendered SVG chart-data helpers for run_detail.html.

Decision and rationale: docs/adr/0006-dashboard-web-charting-server-rendered-svg.md
(RAV-001). This module is the one shared place RAV-002 (model-vs-Naive0 error
chart) and RAV-003 (DM-verdict chart, future) must both build their
pixel-coordinate data from -- pure Python, no I/O, no Jinja2 import, so it is
unit-testable in isolation from the HTTP layer (`app/routers/runs.py` calls
both `build_error_chart`/`build_dm_verdict_chart`; `app/templates/
_error_chart.html`/`_dm_verdict_chart.html` render their respective output).

RAV-002: `build_error_chart` takes the already-fetched, already-parsed list
of `SplitResultResponse` (`run_detail`'s existing `GET /runs/{id}/splits`
call -- no new backend call, no new field) and returns pre-computed SVG bar
geometry for `model_mae` vs `naive0_mae` per split. MAE only this ticket --
RAV-004 (a metric selector for the other six model/naive0 metric pairs) is
out of scope here.

RAV-004: `build_error_chart` now takes a `metric` key (default `"mae"`, kept
for backward compatibility with RAV-002's callers/tests) looked up in
`METRIC_REGISTRY` below -- a name -> (label, model attr name, naive0 attr
name) mapping covering all seven `SplitResultResponse` metric pairs (`mae`,
`rmse`, `smape`, `mase`, `da`, `f1`, `oos_r2`) -- instead of the hardcoded
`.model_mae`/`.naive0_mae` attribute access. `da`/`f1` are labeled
"Directional accuracy"/"F1" (their real statistical meaning), never
hit-rate/win-rate trading language, per this ticket's Analysis section. An
unrecognized `metric` key falls back to `"mae"` here too, so a caller (the
route) that already validated/defaulted an invalid query param still gets a
safe result even if it didn't.

RAV-003: `build_dm_verdict_chart` takes the same already-fetched split list
and buckets each split's existing `dm_verdict` field (verbatim, never
recomputed here) into one of four categories -- the three real `Verdict`
values from `naive_first_engine.dm_test` ("better", "worse", "no significant
difference") plus a fourth sentinel, `UNDEFINED_VERDICT_CATEGORY`, for the
documented `dm_statistic is None and dm_pvalue is None` case (a
single-test-point split's genuinely undefined DM statistic --
`SplitResultResponse`'s own docstring in
`libs/common/src/naive_first_common/contracts.py`). This ticket's chart is a
categorical count chart (verdict -> number of splits), a different scaling
problem than RAV-002's continuous MAE-value bars (bar height there scales
with a raw metric value; here it scales with an integer count over a fixed
four-category domain) -- no shared "scale a value to pixel range" helper
existed to reuse from RAV-002, so none was extracted (disclosed
non-duplication, not a DRY violation).

RAV-009: `build_trend_chart` takes a list of `(RunSummaryResponse,
list[SplitResultResponse])` pairs -- already-`completed`-filtered by the
route, per its own Design section -- and a `metric` key, reusing
`METRIC_REGISTRY` (RAV-004) for the label/attr lookup rather than a second
metric-name mapping. One bar-group per run (not per split): the plotted value
is the mean of the chosen metric across that run's own splits, since this
chart compares *runs* of a repeated configuration against each other, not
splits within one run (a per-split breakdown for each run would be a
different, denser chart this ticket does not build -- documented choice per
the ticket's own Design section). A run with zero splits (should not happen
for a `completed` run, but this function stays total regardless, matching
`build_error_chart`/`build_dm_verdict_chart`'s own convention) contributes no
bar. Reuses the exact same `Bar` dataclass shape RAV-002 already established
(no third bar-geometry implementation) and the same two-series (model,
naive0) status-neutral convention -- no client-baseline series here, since
`RunSummaryResponse` carries no `client_baseline` field. Framed throughout as
"variation across completed runs," never "trend"/forecast language (this
ticket's Analysis/Design sections; CLAUDE.md's positioning constraint).

RAV-005: both functions gain an optional third/second series for the
run's `client_baseline` (VS-017), present on a `SplitResultResponse` only
when the run was submitted with a `client_prediction_reference`.
`build_error_chart` appends a third `client` `Bar` per split, read off
`split.client_baseline.<resolved_metric>` (the registry's metric key name
itself -- `ClientBaselineResult`'s fields are unprefixed, unlike
`model_*`/`naive0_*`) -- only when at least one split in the run carries a
`client_baseline`; `build_dm_verdict_chart` buckets `client_baseline`'s own
`dm_verdict` into the same four categories as a second `client_bars` count
set, reusing `_verdict_category` against `client_baseline` itself (it
carries the same `dm_statistic`/`dm_pvalue`/`dm_verdict` field names as a
split) rather than a second None-check. When no split carries a
`client_baseline`, both functions return exactly the same shape (same bar
geometry, `client`/`client_bars` empty/`None`) as before this ticket -- no
layout change for the common case.
"""

from __future__ import annotations

from dataclasses import dataclass

from naive_first_common.contracts import RunSummaryResponse, SplitResultResponse

_CHART_WIDTH = 640
_CHART_HEIGHT = 220
_PADDING_LEFT = 40
_PADDING_RIGHT = 16
_PADDING_TOP = 16
_PADDING_BOTTOM = 32
_BAR_GAP = 4
_GROUP_GAP = 12
_MIN_BAR_WIDTH = 1.0


@dataclass(frozen=True)
class Bar:
    """One rendered `<rect>`'s geometry plus the raw value it represents (the
    raw value is carried through so the template/tests can assert against the
    real number, not just the scaled pixel height).
    """

    x: float
    y: float
    width: float
    height: float
    value: float


@dataclass(frozen=True)
class SplitBars:
    split_index: int
    model: Bar
    naive0: Bar
    label_x: float
    client: Bar | None = None


@dataclass(frozen=True)
class ErrorChartData:
    width: int
    height: int
    plot_bottom: float
    max_value: float
    splits: list[SplitBars]
    metric: str
    metric_label: str
    has_client_baseline: bool = False
    client_baseline_disclaimer: str | None = None


# RAV-004: metric name -> (chart label, model attr name, naive0 attr name),
# covering all seven `SplitResultResponse` metric pairs. `da`/`f1` are
# labeled with their real statistical meaning ("Directional accuracy"/"F1"),
# never reworded into hit-rate/win-rate trading language (this ticket's
# Analysis section) -- the single place that constraint is enforced, so the
# route/template never hand-roll their own label/attr-name strings.
METRIC_REGISTRY: dict[str, tuple[str, str, str]] = {
    "mae": ("MAE", "model_mae", "naive0_mae"),
    "rmse": ("RMSE", "model_rmse", "naive0_rmse"),
    "smape": ("sMAPE", "model_smape", "naive0_smape"),
    "mase": ("MASE", "model_mase", "naive0_mase"),
    "da": ("Directional accuracy", "model_da", "naive0_da"),
    "f1": ("F1", "model_f1", "naive0_f1"),
    "oos_r2": ("OOS R2", "model_oos_r2", "naive0_oos_r2"),
}

DEFAULT_METRIC = "mae"


def build_error_chart(
    splits: list[SplitResultResponse], metric: str = DEFAULT_METRIC
) -> ErrorChartData:
    """Pre-computes bar geometry for a model-vs-Naive0 error-by-split chart.

    Both series share one y-scale (`max_value` = the larger of every model/
    naive0 value for the selected `metric` across all splits) so relative bar
    heights are directly comparable -- the mandatory-naive-baseline rule this
    platform's own validation protocol requires (naive shown alongside, never
    a model-only chart). An empty `splits` list returns an empty chart (zero
    bars, zero-height plot) rather than raising -- `run_detail.html`'s caller
    never invokes this for a zero-split run (the existing "no splits yet"
    branch handles that), but this function stays total regardless.

    `metric` is looked up in `METRIC_REGISTRY`; an unrecognized key falls
    back to `DEFAULT_METRIC` ("mae") rather than raising, matching the
    route's own "display preference, not a form submission" fallback
    (RAV-004 Design section).
    """
    metric_label, model_attr, naive0_attr = METRIC_REGISTRY.get(
        metric, METRIC_REGISTRY[DEFAULT_METRIC]
    )
    resolved_metric = metric if metric in METRIC_REGISTRY else DEFAULT_METRIC

    plot_width = _CHART_WIDTH - _PADDING_LEFT - _PADDING_RIGHT
    plot_height = _CHART_HEIGHT - _PADDING_TOP - _PADDING_BOTTOM
    plot_bottom = float(_PADDING_TOP + plot_height)

    if not splits:
        return ErrorChartData(
            width=_CHART_WIDTH,
            height=_CHART_HEIGHT,
            plot_bottom=plot_bottom,
            max_value=0.0,
            splits=[],
            metric=resolved_metric,
            metric_label=metric_label,
        )

    # RAV-005: a third (client-supplied) baseline series is only added when at
    # least one split actually carries a `client_baseline` -- the common,
    # no-client-baseline case must keep RAV-002/004's exact two-bar-per-group
    # geometry (no layout change), per this ticket's Design section.
    has_client_baseline = any(s.client_baseline is not None for s in splits)
    client_baseline_disclaimer = next(
        (s.client_baseline.disclaimer for s in splits if s.client_baseline is not None),
        None,
    )

    values = [max(getattr(s, model_attr), getattr(s, naive0_attr)) for s in splits]
    if has_client_baseline:
        values.extend(
            getattr(s.client_baseline, resolved_metric)
            for s in splits
            if s.client_baseline is not None
        )
    max_value = max(values)
    if max_value <= 0:
        max_value = 1.0

    bars_per_group = 3 if has_client_baseline else 2
    group_width = plot_width / len(splits)
    bar_width = max(
        (group_width - _GROUP_GAP * (bars_per_group - 1)) / bars_per_group,
        _MIN_BAR_WIDTH,
    )

    split_bars: list[SplitBars] = []
    for i, split in enumerate(splits):
        group_x = _PADDING_LEFT + i * group_width

        model_value = getattr(split, model_attr)
        naive0_value = getattr(split, naive0_attr)
        model_height = (model_value / max_value) * plot_height
        naive0_height = (naive0_value / max_value) * plot_height

        model_bar = Bar(
            x=group_x,
            y=plot_bottom - model_height,
            width=bar_width,
            height=model_height,
            value=model_value,
        )
        naive0_bar = Bar(
            x=group_x + bar_width + _BAR_GAP,
            y=plot_bottom - naive0_height,
            width=bar_width,
            height=naive0_height,
            value=naive0_value,
        )

        client_bar: Bar | None = None
        if has_client_baseline and split.client_baseline is not None:
            client_value = getattr(split.client_baseline, resolved_metric)
            client_height = (client_value / max_value) * plot_height
            client_bar = Bar(
                x=group_x + 2 * (bar_width + _BAR_GAP),
                y=plot_bottom - client_height,
                width=bar_width,
                height=client_height,
                value=client_value,
            )

        split_bars.append(
            SplitBars(
                split_index=split.split_index,
                model=model_bar,
                naive0=naive0_bar,
                label_x=group_x + group_width / 2,
                client=client_bar,
            )
        )

    return ErrorChartData(
        width=_CHART_WIDTH,
        height=_CHART_HEIGHT,
        plot_bottom=plot_bottom,
        max_value=max_value,
        splits=split_bars,
        metric=resolved_metric,
        metric_label=metric_label,
        has_client_baseline=has_client_baseline,
        client_baseline_disclaimer=client_baseline_disclaimer,
    )


# RAV-003: DM-verdict-by-split categorical count chart.

UNDEFINED_VERDICT_CATEGORY = "undefined for this split"

_VERDICT_CATEGORIES = (
    "better",
    "worse",
    "no significant difference",
    UNDEFINED_VERDICT_CATEGORY,
)

# CSS class suffix per category -- computed here, not in the template, so the
# partial never needs its own string-munging logic (keeps `charting.py` the
# sole place a category name maps to a rendering detail).
_CATEGORY_CSS_SLUGS = {
    "better": "better",
    "worse": "worse",
    "no significant difference": "no-sig-diff",
    UNDEFINED_VERDICT_CATEGORY: "undefined",
}

_DM_CHART_WIDTH = 640
_DM_CHART_HEIGHT = 220
_DM_PADDING_LEFT = 40
_DM_PADDING_RIGHT = 16
_DM_PADDING_TOP = 16
_DM_PADDING_BOTTOM = 48
_DM_BAR_GAP = 16


@dataclass(frozen=True)
class VerdictBar:
    """One category's rendered `<rect>` geometry plus the category label and
    its raw split count (carried through so the template/tests can assert
    against the real count, not just the scaled pixel height).
    """

    category: str
    css_slug: str
    x: float
    y: float
    width: float
    height: float
    count: int
    label_x: float


@dataclass(frozen=True)
class DmVerdictChartData:
    width: int
    height: int
    plot_bottom: float
    max_count: int
    bars: list[VerdictBar]
    client_bars: list[VerdictBar] = ()
    has_client_baseline: bool = False
    client_baseline_disclaimer: str | None = None


def _verdict_category(split: SplitResultResponse) -> str:
    """Maps one split's existing `dm_verdict` field to one of the four chart
    categories, verbatim -- no recomputation of the verdict here, that
    already ran upstream in `naive_first_engine`/`validation-service`. The
    `None`/`None` case (a single-test-point split's genuinely undefined DM
    statistic, per `SplitResultResponse`'s own docstring) always maps to
    `UNDEFINED_VERDICT_CATEGORY`, regardless of whatever string `dm_verdict`
    happens to hold for that row -- it must never be silently dropped or
    merged into "no significant difference".
    """
    if split.dm_statistic is None and split.dm_pvalue is None:
        return UNDEFINED_VERDICT_CATEGORY
    return split.dm_verdict


def verdict_category_and_css_slug(split: SplitResultResponse) -> tuple[str, str]:
    """FHS-003: exposes the same per-split category/slug mapping
    `build_dm_verdict_chart` uses internally, for the new per-horizon
    validation summary panel (`_forecast_horizon_summary_panel.html`), which
    needs a per-split (not aggregated-count) verdict category -- reuses
    `_verdict_category`/`_CATEGORY_CSS_SLUGS`/`UNDEFINED_VERDICT_CATEGORY`
    rather than re-deriving the None-DM-value rule a second time.
    """
    category = _verdict_category(split)
    return category, _CATEGORY_CSS_SLUGS[category]


def build_dm_verdict_chart(splits: list[SplitResultResponse]) -> DmVerdictChartData:
    """Pre-computes bar geometry for a DM-verdict-count-by-category chart.

    One bar per one of the four fixed categories (`_VERDICT_CATEGORIES`),
    height scaled to the largest single-category count across the run's
    splits -- an empty `splits` list returns an empty chart (zero bars,
    zero-height plot) rather than raising, matching `build_error_chart`'s own
    total-function convention above.
    """
    plot_width = _DM_CHART_WIDTH - _DM_PADDING_LEFT - _DM_PADDING_RIGHT
    plot_height = _DM_CHART_HEIGHT - _DM_PADDING_TOP - _DM_PADDING_BOTTOM
    plot_bottom = float(_DM_PADDING_TOP + plot_height)

    if not splits:
        return DmVerdictChartData(
            width=_DM_CHART_WIDTH,
            height=_DM_CHART_HEIGHT,
            plot_bottom=plot_bottom,
            max_count=0,
            bars=[],
        )

    # RAV-005: a second, distinguishable bucketed count set for the optional
    # client-supplied baseline's own `dm_verdict`, reusing `_verdict_category`
    # (RAV-003) against `client_baseline` itself (it carries the same
    # `dm_statistic`/`dm_pvalue`/`dm_verdict` field names as a split) rather
    # than a second, inconsistent None-check.
    has_client_baseline = any(s.client_baseline is not None for s in splits)
    client_baseline_disclaimer = next(
        (s.client_baseline.disclaimer for s in splits if s.client_baseline is not None),
        None,
    )

    counts = {category: 0 for category in _VERDICT_CATEGORIES}
    client_counts = {category: 0 for category in _VERDICT_CATEGORIES}
    for split in splits:
        counts[_verdict_category(split)] += 1
        if split.client_baseline is not None:
            client_counts[_verdict_category(split.client_baseline)] += 1

    max_count = max(counts.values())
    if max_count <= 0:
        max_count = 1

    max_client_count = max(client_counts.values()) if has_client_baseline else 0
    if has_client_baseline and max_client_count <= 0:
        max_client_count = 1

    bar_width = (plot_width - _DM_BAR_GAP * (len(_VERDICT_CATEGORIES) - 1)) / len(
        _VERDICT_CATEGORIES
    )

    bars: list[VerdictBar] = []
    for i, category in enumerate(_VERDICT_CATEGORIES):
        count = counts[category]
        height = (count / max_count) * plot_height
        x = _DM_PADDING_LEFT + i * (bar_width + _DM_BAR_GAP)
        bars.append(
            VerdictBar(
                category=category,
                css_slug=_CATEGORY_CSS_SLUGS[category],
                x=x,
                y=plot_bottom - height,
                width=bar_width,
                height=height,
                count=count,
                label_x=x + bar_width / 2,
            )
        )

    client_bars: list[VerdictBar] = []
    if has_client_baseline:
        for i, category in enumerate(_VERDICT_CATEGORIES):
            count = client_counts[category]
            height = (count / max_client_count) * plot_height
            x = _DM_PADDING_LEFT + i * (bar_width + _DM_BAR_GAP)
            client_bars.append(
                VerdictBar(
                    category=category,
                    css_slug=_CATEGORY_CSS_SLUGS[category],
                    x=x,
                    y=plot_bottom - height,
                    width=bar_width,
                    height=height,
                    count=count,
                    label_x=x + bar_width / 2,
                )
            )

    return DmVerdictChartData(
        width=_DM_CHART_WIDTH,
        height=_DM_CHART_HEIGHT,
        plot_bottom=plot_bottom,
        max_count=max_count,
        bars=bars,
        client_bars=client_bars,
        has_client_baseline=has_client_baseline,
        client_baseline_disclaimer=client_baseline_disclaimer,
    )


# RAV-009: cross-run variation chart -- one bar-group per completed run of a
# repeated (dataset_id, horizon) configuration, not per split.

_TREND_CHART_WIDTH = 640
_TREND_CHART_HEIGHT = 220
_TREND_PADDING_LEFT = 40
_TREND_PADDING_RIGHT = 16
_TREND_PADDING_TOP = 16
_TREND_PADDING_BOTTOM = 32
_TREND_BAR_GAP = 4
_TREND_GROUP_GAP = 12
_TREND_MIN_BAR_WIDTH = 1.0


@dataclass(frozen=True)
class RunBars:
    """One run's rendered model/naive0 bar pair, plus the run id so the
    template/tests can label each group by the actual run being compared --
    same shape as `SplitBars` above, keyed by run rather than split.
    """

    run_id: str
    model: Bar
    naive0: Bar
    label_x: float


@dataclass(frozen=True)
class TrendChartData:
    width: int
    height: int
    plot_bottom: float
    max_value: float
    runs: list[RunBars]
    metric: str
    metric_label: str


def _mean_metric(splits: list[SplitResultResponse], attr: str) -> float | None:
    values = [getattr(split, attr) for split in splits]
    if not values:
        return None
    return sum(values) / len(values)


def build_trend_chart(
    runs: list[tuple[RunSummaryResponse, list[SplitResultResponse]]],
    metric: str = DEFAULT_METRIC,
) -> TrendChartData:
    """Pre-computes bar geometry for a "how this configuration's validation
    results have varied across completed runs" chart -- backward-looking
    only, never a forecast of a future run's outcome (this ticket's Design
    section). `runs` is the caller's already-`completed`-filtered list of
    `(RunSummaryResponse, splits)` pairs (the route below is the one place
    that filter is applied, per the mandatory-naive-baseline reasoning
    `runs_horizon_summary` (FHS-002) already established for excluding
    `running`/`failed` runs -- not re-applied here so this function stays a
    pure aggregation over whatever it is handed, matching
    `build_error_chart`/`build_dm_verdict_chart`'s own total-function
    convention).

    One bar-group per run: the plotted value is the mean of the chosen
    metric across that run's own splits (ticket Design section's documented
    choice -- a run-level summary, not a second per-split breakdown). A run
    contributing zero splits is skipped (no bar), rather than plotting a
    fabricated zero.
    """
    metric_label, model_attr, naive0_attr = METRIC_REGISTRY.get(
        metric, METRIC_REGISTRY[DEFAULT_METRIC]
    )
    resolved_metric = metric if metric in METRIC_REGISTRY else DEFAULT_METRIC

    plot_width = _TREND_CHART_WIDTH - _TREND_PADDING_LEFT - _TREND_PADDING_RIGHT
    plot_height = _TREND_CHART_HEIGHT - _TREND_PADDING_TOP - _TREND_PADDING_BOTTOM
    plot_bottom = float(_TREND_PADDING_TOP + plot_height)

    run_values: list[tuple[RunSummaryResponse, float, float]] = []
    for run, splits in runs:
        model_mean = _mean_metric(splits, model_attr)
        naive0_mean = _mean_metric(splits, naive0_attr)
        if model_mean is None or naive0_mean is None:
            continue
        run_values.append((run, model_mean, naive0_mean))

    if not run_values:
        return TrendChartData(
            width=_TREND_CHART_WIDTH,
            height=_TREND_CHART_HEIGHT,
            plot_bottom=plot_bottom,
            max_value=0.0,
            runs=[],
            metric=resolved_metric,
            metric_label=metric_label,
        )

    max_value = max(max(model_mean, naive0_mean) for _run, model_mean, naive0_mean in run_values)
    if max_value <= 0:
        max_value = 1.0

    group_width = plot_width / len(run_values)
    bar_width = max(
        (group_width - _TREND_BAR_GAP) / 2,
        _TREND_MIN_BAR_WIDTH,
    )

    run_bars: list[RunBars] = []
    for i, (run, model_mean, naive0_mean) in enumerate(run_values):
        group_x = _TREND_PADDING_LEFT + i * group_width

        model_height = (model_mean / max_value) * plot_height
        naive0_height = (naive0_mean / max_value) * plot_height

        model_bar = Bar(
            x=group_x,
            y=plot_bottom - model_height,
            width=bar_width,
            height=model_height,
            value=model_mean,
        )
        naive0_bar = Bar(
            x=group_x + bar_width + _TREND_BAR_GAP,
            y=plot_bottom - naive0_height,
            width=bar_width,
            height=naive0_height,
            value=naive0_mean,
        )

        run_bars.append(
            RunBars(
                run_id=run.id,
                model=model_bar,
                naive0=naive0_bar,
                label_x=group_x + group_width / 2,
            )
        )

    return TrendChartData(
        width=_TREND_CHART_WIDTH,
        height=_TREND_CHART_HEIGHT,
        plot_bottom=plot_bottom,
        max_value=max_value,
        runs=run_bars,
        metric=resolved_metric,
        metric_label=metric_label,
    )


# RAV-010: consistency indicator -- "beat Naive0 in N of M completed runs" for
# a selected (dataset_id, horizon) group, computed client-side (dashboard-web)
# from already-fetched `dm_verdict` values (no new backend statistic, no new
# significance test -- only counts verdicts `naive_first_engine`'s own
# Harvey-corrected DM test already computed upstream).


@dataclass(frozen=True)
class ConsistencyIndicator:
    """`has_data` distinguishes "zero runs matched the selection" from a
    genuine "0 of 0" -- the route must render a plain "no data" message in
    the former case, never a fabricated ratio (this ticket's Implementation
    acceptance criteria).
    """

    beat_count: int
    total_count: int
    has_data: bool


def _run_beats_naive0(splits: list[SplitResultResponse]) -> bool | None:
    """Majority rule (this ticket's Analysis section, documented explicitly
    per its own instruction): a run counts as having beaten Naive0 if strictly
    more of its splits fall in the "better" category than in "worse" and "no
    significant difference" *combined*. Splits whose DM statistic is
    genuinely undefined (`UNDEFINED_VERDICT_CATEGORY`, via `_verdict_category`
    -- RAV-003's None/None rule) are excluded from both sides of that count,
    never counted as "worse"/"no significant difference" by default, per this
    ticket's Design section. A run with no split available for the count (all
    splits undefined, or zero splits) returns `None` -- it does not count
    toward `beat_count` or `total_count`, since there is nothing to evaluate
    a majority over.
    """
    better = 0
    other = 0
    for split in splits:
        category = _verdict_category(split)
        if category == UNDEFINED_VERDICT_CATEGORY:
            continue
        if category == "better":
            better += 1
        else:
            other += 1
    if better + other == 0:
        return None
    return better > other


def compute_consistency_indicator(
    runs: list[tuple[RunSummaryResponse, list[SplitResultResponse]]],
) -> ConsistencyIndicator:
    """Counts, across the caller's already-`completed`-filtered, already-
    fetched `(RunSummaryResponse, splits)` pairs (RAV-009's own trend-view
    fetch -- no second `GET /runs/{id}/splits` call here), how many runs had
    a majority "better"-than-Naive0 verdict across their own splits, per
    `_run_beats_naive0`'s documented rule.

    An empty `runs` list, or a `runs` list where every run has no evaluable
    split (all splits `UNDEFINED_VERDICT_CATEGORY`, or zero splits), returns
    `has_data=False` -- the route/template must render "no completed runs
    matched this selection" rather than a fabricated "0 of 0" (this ticket's
    Implementation acceptance criteria).
    """
    beat_count = 0
    total_count = 0
    for _run, splits in runs:
        result = _run_beats_naive0(splits)
        if result is None:
            continue
        total_count += 1
        if result:
            beat_count += 1

    return ConsistencyIndicator(
        beat_count=beat_count,
        total_count=total_count,
        has_data=total_count > 0,
    )
