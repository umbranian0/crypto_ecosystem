from naive_first_common.consistency import (
    UNDEFINED_VERDICT_CATEGORY,
    ConsistencyIndicator,
    compute_consistency_indicator,
    run_beats_naive0,
    verdict_category,
)
from naive_first_common.contracts import SplitResultResponse

_BASE = {
    "train_start": "2026-01-01T00:00:00Z",
    "train_end": "2026-01-10T00:00:00Z",
    "purge_start": "2026-01-10T00:00:00Z",
    "purge_end": "2026-01-10T06:00:00Z",
    "test_start": "2026-01-10T06:00:00Z",
    "test_end": "2026-01-11T00:00:00Z",
    "model_mae": 1.0,
    "model_rmse": 2.2,
    "model_smape": 3.3,
    "model_mase": 4.4,
    "model_da": 0.5,
    "model_f1": 0.6,
    "model_oos_r2": 0.1,
    "naive0_mae": 2.0,
    "naive0_rmse": 2.0,
    "naive0_smape": 3.0,
    "naive0_mase": 4.0,
    "naive0_da": 0.51,
    "naive0_f1": 0.61,
    "naive0_oos_r2": 0.12,
}


def _split(verdict: str, *, undefined: bool = False) -> SplitResultResponse:
    return SplitResultResponse(
        split_index=0,
        dm_statistic=None if undefined else -0.9,
        dm_pvalue=None if undefined else 0.42,
        dm_verdict=verdict,
        **_BASE,
    )


def _run(*verdicts: str, undefined: int = 0):
    splits = [_split(v) for v in verdicts] + [
        _split("no significant difference", undefined=True) for _ in range(undefined)
    ]
    return ("run", splits)


def test_verdict_category_undefined_ignores_verdict_string() -> None:
    assert verdict_category(_split("better", undefined=True)) == UNDEFINED_VERDICT_CATEGORY
    assert verdict_category(_split("worse")) == "worse"


def test_empty_runs_has_no_data() -> None:
    assert compute_consistency_indicator([]) == ConsistencyIndicator(0, 0, False)


def test_majority_better_counts_as_beat() -> None:
    result = compute_consistency_indicator([_run("better", "better", "worse")])

    assert result == ConsistencyIndicator(beat_count=1, total_count=1, has_data=True)


def test_undefined_splits_are_excluded_from_both_sides() -> None:
    assert run_beats_naive0(_run("better", undefined=5)[1]) is True


def test_all_undefined_run_is_not_evaluable() -> None:
    assert run_beats_naive0(_run(undefined=3)[1]) is None
    assert compute_consistency_indicator([_run(undefined=3)]).has_data is False


def test_tie_is_not_a_beat() -> None:
    result = compute_consistency_indicator([_run("better", "worse")])

    assert result == ConsistencyIndicator(beat_count=0, total_count=1, has_data=True)


def test_better_must_beat_worse_and_no_sig_combined() -> None:
    assert run_beats_naive0(_run("better", "worse", "no significant difference")[1]) is False


def test_zero_splits_run_not_evaluable_and_not_counted() -> None:
    assert run_beats_naive0([]) is None
    result = compute_consistency_indicator([_run(), _run("better")])

    assert result == ConsistencyIndicator(beat_count=1, total_count=1, has_data=True)
