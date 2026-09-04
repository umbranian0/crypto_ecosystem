"""RAV-002: unit tests for `app.charting.build_error_chart` -- pure function,
no HTTP, no Jinja2, per docs/adr/0006-dashboard-web-charting-server-rendered-svg.md.
"""

from __future__ import annotations

from naive_first_common.contracts import SplitResultResponse

from app.charting import UNDEFINED_VERDICT_CATEGORY, build_dm_verdict_chart, build_error_chart

_BASE_SPLIT_FIELDS = {
    "train_start": "2026-01-01T00:00:00Z",
    "train_end": "2026-01-10T00:00:00Z",
    "purge_start": "2026-01-10T00:00:00Z",
    "purge_end": "2026-01-10T06:00:00Z",
    "test_start": "2026-01-10T06:00:00Z",
    "test_end": "2026-01-11T00:00:00Z",
    "model_rmse": 2.2,
    "model_smape": 3.3,
    "model_mase": 4.4,
    "model_da": 0.5,
    "model_f1": 0.6,
    "model_oos_r2": 0.1,
    "naive0_rmse": 2.0,
    "naive0_smape": 3.0,
    "naive0_mase": 4.0,
    "naive0_da": 0.51,
    "naive0_f1": 0.61,
    "naive0_oos_r2": 0.12,
    "dm_statistic": -0.9,
    "dm_pvalue": 0.42,
    "dm_verdict": "no significant difference",
}


def _split(split_index: int, model_mae: float, naive0_mae: float) -> SplitResultResponse:
    return SplitResultResponse(
        split_index=split_index,
        model_mae=model_mae,
        naive0_mae=naive0_mae,
        **_BASE_SPLIT_FIELDS,
    )


def test_build_error_chart_empty_splits() -> None:
    chart = build_error_chart([])

    assert chart.splits == []
    assert chart.max_value == 0.0


def test_build_error_chart_bar_heights_match_relative_values() -> None:
    splits = [_split(0, model_mae=1.0, naive0_mae=2.0), _split(1, model_mae=4.0, naive0_mae=2.0)]

    chart = build_error_chart(splits)

    assert chart.max_value == 4.0
    assert len(chart.splits) == 2

    # Split 0: model (1.0) is half of naive0 (2.0) -> half the bar height.
    split_0 = chart.splits[0]
    assert split_0.model.value == 1.0
    assert split_0.naive0.value == 2.0
    assert split_0.model.height == split_0.naive0.height / 2

    # Split 1: model (4.0) equals the chart's max_value -> fills the full plot height.
    split_1 = chart.splits[1]
    assert split_1.model.value == 4.0
    assert split_1.model.height > split_1.naive0.height

    # Taller bars sit higher (smaller y) since the chart grows up from a fixed baseline.
    assert split_1.model.y < split_1.naive0.y
    assert split_1.model.y + split_1.model.height == chart.plot_bottom
    assert split_1.naive0.y + split_1.naive0.height == chart.plot_bottom


def test_build_error_chart_bars_do_not_overlap_within_a_split() -> None:
    splits = [_split(0, model_mae=1.0, naive0_mae=2.0)]

    chart = build_error_chart(splits)
    bar = chart.splits[0]

    assert bar.model.x + bar.model.width <= bar.naive0.x


def test_build_error_chart_zero_error_splits_do_not_divide_by_zero() -> None:
    splits = [_split(0, model_mae=0.0, naive0_mae=0.0)]

    chart = build_error_chart(splits)

    assert chart.max_value == 1.0
    assert chart.splits[0].model.height == 0.0
    assert chart.splits[0].naive0.height == 0.0


def _dm_split(
    split_index: int,
    dm_statistic: float | None,
    dm_pvalue: float | None,
    dm_verdict: str,
) -> SplitResultResponse:
    fields = {**_BASE_SPLIT_FIELDS}
    fields["dm_statistic"] = dm_statistic
    fields["dm_pvalue"] = dm_pvalue
    fields["dm_verdict"] = dm_verdict
    return SplitResultResponse(
        split_index=split_index,
        model_mae=1.0,
        naive0_mae=1.0,
        **fields,
    )


def test_build_dm_verdict_chart_empty_splits() -> None:
    chart = build_dm_verdict_chart([])

    assert chart.bars == []
    assert chart.max_count == 0


def test_build_dm_verdict_chart_buckets_all_four_categories() -> None:
    """RAV-003: a fixture with all three real `Verdict` strings plus a
    `dm_statistic=None, dm_pvalue=None` split -- the `None` case must land in
    its own `UNDEFINED_VERDICT_CATEGORY` bucket, never dropped or merged into
    "no significant difference".
    """
    splits = [
        _dm_split(0, -2.5, 0.01, "better"),
        _dm_split(1, 2.5, 0.01, "worse"),
        _dm_split(2, -0.9, 0.42, "no significant difference"),
        _dm_split(3, None, None, "no significant difference"),
    ]

    chart = build_dm_verdict_chart(splits)

    counts = {bar.category: bar.count for bar in chart.bars}
    assert counts["better"] == 1
    assert counts["worse"] == 1
    assert counts["no significant difference"] == 1
    assert counts[UNDEFINED_VERDICT_CATEGORY] == 1
    assert chart.max_count == 1
    # Exactly four categories are always rendered, even ones with a zero count.
    assert len(chart.bars) == 4


def test_build_dm_verdict_chart_none_dm_never_merged_into_no_sig_diff() -> None:
    """Even though the fixture's raw `dm_verdict` string for the null-DM split
    says "no significant difference" (a real, documented case -- the upstream
    verdict field is still populated even when the statistic is undefined),
    the chart must categorize it separately based on the `None`/`None` check,
    not the raw string.
    """
    splits = [
        _dm_split(0, None, None, "no significant difference"),
        _dm_split(1, -0.9, 0.42, "no significant difference"),
    ]

    chart = build_dm_verdict_chart(splits)
    counts = {bar.category: bar.count for bar in chart.bars}

    assert counts[UNDEFINED_VERDICT_CATEGORY] == 1
    assert counts["no significant difference"] == 1


def test_build_dm_verdict_chart_bar_heights_scale_to_max_count() -> None:
    splits = [
        _dm_split(0, -2.5, 0.01, "better"),
        _dm_split(1, -2.6, 0.01, "better"),
        _dm_split(2, 2.5, 0.01, "worse"),
    ]

    chart = build_dm_verdict_chart(splits)
    bars = {bar.category: bar for bar in chart.bars}

    assert chart.max_count == 2
    assert bars["better"].height > bars["worse"].height
    assert bars["no significant difference"].height == 0.0
    assert bars[UNDEFINED_VERDICT_CATEGORY].height == 0.0
