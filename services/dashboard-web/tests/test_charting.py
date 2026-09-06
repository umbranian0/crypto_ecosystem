"""RAV-002: unit tests for `app.charting.build_error_chart` -- pure function,
no HTTP, no Jinja2, per docs/adr/0006-dashboard-web-charting-server-rendered-svg.md.
"""

from __future__ import annotations

import pytest
from naive_first_common.contracts import (
    ClientBaselineResult,
    RunSummaryResponse,
    SplitResultResponse,
)

from app.charting import (
    METRIC_REGISTRY,
    UNDEFINED_VERDICT_CATEGORY,
    build_dm_verdict_chart,
    build_error_chart,
    build_trend_chart,
    compute_consistency_indicator,
)

_DISCLAIMER = (
    "This client-supplied baseline is shown for reference only and is not "
    "validated by this platform."
)


def _client_baseline(
    mae: float = 0.9,
    dm_statistic: float | None = -1.2,
    dm_pvalue: float | None = 0.03,
    dm_verdict: str = "better",
) -> ClientBaselineResult:
    return ClientBaselineResult(
        key="client",
        mae=mae,
        rmse=1.0,
        smape=1.0,
        mase=1.0,
        da=0.5,
        f1=0.5,
        oos_r2=0.1,
        dm_statistic=dm_statistic,
        dm_pvalue=dm_pvalue,
        dm_verdict=dm_verdict,
        disclaimer=_DISCLAIMER,
    )

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


def _run_summary(run_id: str, status: str = "completed") -> RunSummaryResponse:
    return RunSummaryResponse(
        id=run_id,
        dataset_id="dataset-1",
        horizon=24,
        status=status,
        created_at="2026-08-01T00:00:00Z",
        completed_at="2026-08-01T01:00:00Z" if status == "completed" else None,
    )


def test_build_trend_chart_empty_runs() -> None:
    chart = build_trend_chart([])

    assert chart.runs == []
    assert chart.max_value == 0.0


def test_build_trend_chart_only_plots_completed_runs_and_uses_mean_metric() -> None:
    """RAV-009 Test acceptance criteria: a fixture set of runs, some
    `completed`, some `running`/`failed`, sharing a `dataset_id`/`horizon` --
    only `completed` runs are plotted, and the plotted value is the mean of
    the chosen metric across that run's own splits (Design section's
    documented per-run aggregation choice).
    """
    completed_run = _run_summary("run-completed")
    running_run = _run_summary("run-running", status="running")
    failed_run = _run_summary("run-failed", status="failed")

    completed_splits = [
        _split(0, model_mae=1.0, naive0_mae=2.0),
        _split(1, model_mae=3.0, naive0_mae=4.0),
    ]

    # Only `completed_run` is passed with real splits -- callers are expected
    # to already filter to `completed` runs (route's own responsibility,
    # per this ticket's Design section); a `running`/`failed` run with no
    # splits fetched (empty list, the route never calls `/splits` for them)
    # contributes no bar either way, asserted below by its absence.
    runs = [
        (completed_run, completed_splits),
        (running_run, []),
        (failed_run, []),
    ]

    chart = build_trend_chart(runs, metric="mae")

    assert len(chart.runs) == 1
    assert chart.runs[0].run_id == "run-completed"
    assert chart.runs[0].model.value == 2.0  # mean(1.0, 3.0)
    assert chart.runs[0].naive0.value == 3.0  # mean(2.0, 4.0)
    assert chart.metric == "mae"
    assert chart.metric_label == "MAE"


def test_build_trend_chart_multiple_completed_runs_bar_heights_reflect_mean_values() -> None:
    run_a = _run_summary("run-a")
    run_b = _run_summary("run-b")

    runs = [
        (run_a, [_split(0, model_mae=1.0, naive0_mae=1.0)]),
        (run_b, [_split(0, model_mae=4.0, naive0_mae=1.0)]),
    ]

    chart = build_trend_chart(runs, metric="mae")

    assert chart.max_value == 4.0
    assert len(chart.runs) == 2
    assert chart.runs[0].model.height == chart.runs[0].naive0.height
    assert chart.runs[1].model.height > chart.runs[1].naive0.height
    assert chart.runs[1].model.x + chart.runs[1].model.width <= chart.runs[1].naive0.x


def test_build_trend_chart_unrecognized_metric_falls_back_to_mae() -> None:
    run_a = _run_summary("run-a")
    runs = [(run_a, [_split(0, model_mae=1.0, naive0_mae=2.0)])]

    chart = build_trend_chart(runs, metric="not-a-real-metric")

    assert chart.metric == "mae"
    assert chart.metric_label == "MAE"


def test_build_error_chart_zero_error_splits_do_not_divide_by_zero() -> None:
    splits = [_split(0, model_mae=0.0, naive0_mae=0.0)]

    chart = build_error_chart(splits)

    assert chart.max_value == 1.0
    assert chart.splits[0].model.height == 0.0
    assert chart.splits[0].naive0.height == 0.0


def test_build_error_chart_default_metric_is_mae() -> None:
    splits = [_split(0, model_mae=1.0, naive0_mae=2.0)]

    chart = build_error_chart(splits)

    assert chart.metric == "mae"
    assert chart.metric_label == "MAE"


@pytest.mark.parametrize("metric", sorted(METRIC_REGISTRY))
def test_build_error_chart_metric_selector_all_seven_pairs(metric: str) -> None:
    """RAV-004: parametrized over all seven `SplitResultResponse` metric
    pairs -- bar values must match the fixture's real `model_<metric>`/
    `naive0_<metric>` values, not just MAE.
    """
    fields = {**_BASE_SPLIT_FIELDS, "model_mae": 1.1, "naive0_mae": 1.0}
    split = SplitResultResponse(split_index=0, **fields)

    chart = build_error_chart([split], metric=metric)

    _label, model_attr, naive0_attr = METRIC_REGISTRY[metric]
    assert chart.metric == metric
    assert chart.metric_label == METRIC_REGISTRY[metric][0]
    assert chart.splits[0].model.value == getattr(split, model_attr)
    assert chart.splits[0].naive0.value == getattr(split, naive0_attr)


def test_build_error_chart_unrecognized_metric_falls_back_to_mae() -> None:
    splits = [_split(0, model_mae=1.0, naive0_mae=2.0)]

    chart = build_error_chart(splits, metric="not-a-real-metric")

    assert chart.metric == "mae"
    assert chart.metric_label == "MAE"
    assert chart.splits[0].model.value == 1.0
    assert chart.splits[0].naive0.value == 2.0


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


# RAV-005: client-supplied baseline overlay.


def test_build_error_chart_no_client_baseline_shape_unchanged() -> None:
    """When no split carries a `client_baseline`, the return shape must be
    byte-for-byte identical to pre-RAV-005 behavior -- no regression against
    RAV-002/004's own existing assertions above.
    """
    splits = [_split(0, model_mae=1.0, naive0_mae=2.0), _split(1, model_mae=4.0, naive0_mae=2.0)]

    chart = build_error_chart(splits)

    assert chart.has_client_baseline is False
    assert chart.client_baseline_disclaimer is None
    for split_bars in chart.splits:
        assert split_bars.client is None


def test_build_error_chart_client_baseline_third_series() -> None:
    fields = {**_BASE_SPLIT_FIELDS, "model_mae": 1.0, "naive0_mae": 2.0}
    split_with_baseline = SplitResultResponse(
        split_index=0, client_baseline=_client_baseline(mae=0.5), **fields
    )
    split_without_baseline = SplitResultResponse(split_index=1, **fields)

    chart = build_error_chart([split_with_baseline, split_without_baseline])

    assert chart.has_client_baseline is True
    assert chart.client_baseline_disclaimer == _DISCLAIMER

    bar_0 = chart.splits[0]
    assert bar_0.client is not None
    assert bar_0.client.value == 0.5
    # Three bars for split 0 must not overlap.
    assert bar_0.model.x + bar_0.model.width <= bar_0.naive0.x
    assert bar_0.naive0.x + bar_0.naive0.width <= bar_0.client.x

    # Split 1 has no client_baseline -- its `client` bar stays None even
    # though the chart overall has_client_baseline.
    bar_1 = chart.splits[1]
    assert bar_1.client is None


def test_build_error_chart_client_baseline_uses_metric_registry_value() -> None:
    fields = {**_BASE_SPLIT_FIELDS, "model_rmse": 2.2, "naive0_rmse": 2.0}
    split = SplitResultResponse(
        split_index=0,
        model_mae=1.0,
        naive0_mae=1.0,
        client_baseline=_client_baseline(),
        **{**fields},
    )
    # Overwrite rmse on the client baseline for this assertion.
    split = split.model_copy(
        update={"client_baseline": split.client_baseline.model_copy(update={"rmse": 1.7})}
    )

    chart = build_error_chart([split], metric="rmse")

    assert chart.splits[0].client.value == 1.7


def test_build_dm_verdict_chart_no_client_baseline_shape_unchanged() -> None:
    splits = [_dm_split(0, -2.5, 0.01, "better")]

    chart = build_dm_verdict_chart(splits)

    assert chart.has_client_baseline is False
    assert chart.client_baseline_disclaimer is None
    assert chart.client_bars == () or chart.client_bars == []


def test_build_dm_verdict_chart_client_baseline_second_series() -> None:
    fields = {**_BASE_SPLIT_FIELDS}
    fields["dm_statistic"] = -0.9
    fields["dm_pvalue"] = 0.42
    fields["dm_verdict"] = "no significant difference"
    split = SplitResultResponse(
        split_index=0,
        model_mae=1.0,
        naive0_mae=1.0,
        client_baseline=_client_baseline(dm_statistic=2.5, dm_pvalue=0.01, dm_verdict="worse"),
        **fields,
    )

    chart = build_dm_verdict_chart([split])

    assert chart.has_client_baseline is True
    assert chart.client_baseline_disclaimer == _DISCLAIMER
    client_counts = {bar.category: bar.count for bar in chart.client_bars}
    assert client_counts["worse"] == 1
    assert client_counts["better"] == 0
    # The platform's own verdict count set is unaffected.
    own_counts = {bar.category: bar.count for bar in chart.bars}
    assert own_counts["no significant difference"] == 1


def test_build_dm_verdict_chart_client_baseline_undefined_dm_not_merged() -> None:
    """A `client_baseline` split with `dm_statistic`/`dm_pvalue` both `None`
    must map to `UNDEFINED_VERDICT_CATEGORY`, never merged into "no
    significant difference" -- the same treatment RAV-003 already defines for
    the platform's own baseline.
    """
    fields = {**_BASE_SPLIT_FIELDS}
    split = SplitResultResponse(
        split_index=0,
        model_mae=1.0,
        naive0_mae=1.0,
        client_baseline=_client_baseline(
            dm_statistic=None, dm_pvalue=None, dm_verdict="no significant difference"
        ),
        **fields,
    )

    chart = build_dm_verdict_chart([split])

    client_counts = {bar.category: bar.count for bar in chart.client_bars}
    assert client_counts[UNDEFINED_VERDICT_CATEGORY] == 1
    assert client_counts["no significant difference"] == 0


# RAV-010: unit tests for `compute_consistency_indicator` -- pure function,
# reuses RAV-009's fixture shape ((RunSummaryResponse, list[SplitResultResponse])
# pairs) and RAV-003's `_dm_split`/`_run_summary` helpers.


def test_compute_consistency_indicator_no_runs_has_no_data() -> None:
    indicator = compute_consistency_indicator([])

    assert indicator.has_data is False
    assert indicator.beat_count == 0
    assert indicator.total_count == 0


def test_compute_consistency_indicator_majority_better_counts_as_beat() -> None:
    """A run with more "better" splits than "worse"/"no significant
    difference" combined counts toward `beat_count`; a run without such a
    majority does not.
    """
    run_better = _run_summary("run-better")
    run_worse = _run_summary("run-worse")

    splits_better = [
        _dm_split(0, -2.0, 0.01, "better"),
        _dm_split(1, -2.0, 0.01, "better"),
        _dm_split(2, 1.0, 0.5, "no significant difference"),
    ]
    splits_worse = [
        _dm_split(0, 2.0, 0.01, "worse"),
        _dm_split(1, -2.0, 0.01, "better"),
    ]

    indicator = compute_consistency_indicator(
        [(run_better, splits_better), (run_worse, splits_worse)]
    )

    assert indicator.has_data is True
    assert indicator.beat_count == 1
    assert indicator.total_count == 2


def test_compute_consistency_indicator_undefined_dm_splits_excluded_from_count() -> None:
    """A run whose splits are entirely `UNDEFINED_VERDICT_CATEGORY` (both DM
    fields `None`) contributes to neither `beat_count` nor `total_count` --
    there is nothing to evaluate a majority over, and it must never be
    silently counted as "worse".
    """
    run_undefined = _run_summary("run-undefined")
    run_better = _run_summary("run-better")

    splits_undefined = [_dm_split(0, None, None, "no significant difference")]
    splits_better = [
        _dm_split(0, -2.0, 0.01, "better"),
        _dm_split(1, None, None, "no significant difference"),
    ]

    indicator = compute_consistency_indicator(
        [(run_undefined, splits_undefined), (run_better, splits_better)]
    )

    assert indicator.has_data is True
    assert indicator.beat_count == 1
    assert indicator.total_count == 1


def test_compute_consistency_indicator_all_runs_undefined_has_no_data() -> None:
    run_undefined = _run_summary("run-undefined")
    splits_undefined = [_dm_split(0, None, None, "no significant difference")]

    indicator = compute_consistency_indicator([(run_undefined, splits_undefined)])

    assert indicator.has_data is False
    assert indicator.beat_count == 0
    assert indicator.total_count == 0
