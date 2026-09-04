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
"""

from __future__ import annotations

from dataclasses import dataclass

from naive_first_common.contracts import SplitResultResponse

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


@dataclass(frozen=True)
class ErrorChartData:
    width: int
    height: int
    plot_bottom: float
    max_value: float
    splits: list[SplitBars]


def build_error_chart(splits: list[SplitResultResponse]) -> ErrorChartData:
    """Pre-computes bar geometry for a model-vs-Naive0 MAE-by-split chart.

    Both series share one y-scale (`max_value` = the larger of every
    `model_mae`/`naive0_mae` across all splits) so relative bar heights are
    directly comparable -- the mandatory-naive-baseline rule this platform's
    own validation protocol requires (naive shown alongside, never a
    model-only chart). An empty `splits` list returns an empty chart (zero
    bars, zero-height plot) rather than raising -- `run_detail.html`'s caller
    never invokes this for a zero-split run (the existing "no splits yet"
    branch handles that), but this function stays total regardless.
    """
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
        )

    max_value = max(max(s.model_mae, s.naive0_mae) for s in splits)
    if max_value <= 0:
        max_value = 1.0

    group_width = plot_width / len(splits)
    bar_width = max((group_width - _GROUP_GAP) / 2, _MIN_BAR_WIDTH)

    split_bars: list[SplitBars] = []
    for i, split in enumerate(splits):
        group_x = _PADDING_LEFT + i * group_width

        model_height = (split.model_mae / max_value) * plot_height
        naive0_height = (split.naive0_mae / max_value) * plot_height

        model_bar = Bar(
            x=group_x,
            y=plot_bottom - model_height,
            width=bar_width,
            height=model_height,
            value=split.model_mae,
        )
        naive0_bar = Bar(
            x=group_x + bar_width + _BAR_GAP,
            y=plot_bottom - naive0_height,
            width=bar_width,
            height=naive0_height,
            value=split.naive0_mae,
        )
        split_bars.append(
            SplitBars(
                split_index=split.split_index,
                model=model_bar,
                naive0=naive0_bar,
                label_x=group_x + group_width / 2,
            )
        )

    return ErrorChartData(
        width=_CHART_WIDTH,
        height=_CHART_HEIGHT,
        plot_bottom=plot_bottom,
        max_value=max_value,
        splits=split_bars,
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

    counts = {category: 0 for category in _VERDICT_CATEGORIES}
    for split in splits:
        counts[_verdict_category(split)] += 1

    max_count = max(counts.values())
    if max_count <= 0:
        max_count = 1

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

    return DmVerdictChartData(
        width=_DM_CHART_WIDTH,
        height=_DM_CHART_HEIGHT,
        plot_bottom=plot_bottom,
        max_count=max_count,
        bars=bars,
    )
