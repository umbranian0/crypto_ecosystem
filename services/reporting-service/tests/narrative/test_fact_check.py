"""AI-002 tests: `app.narrative.fact_check`."""

from __future__ import annotations

from datetime import datetime, timezone

from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

from app.narrative.fact_check import contains_banned_term, is_directionally_consistent


def _make_run() -> RunDetailResponse:
    return RunDetailResponse(
        id="run-1",
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=24,
        purge_gap_hours=24,
        split_config={},
        status="completed",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        failure_reason=None,
    )


def _make_split(dm_verdict: str) -> SplitResultResponse:
    return SplitResultResponse(
        split_index=0,
        train_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        train_end=datetime(2026, 1, 5, tzinfo=timezone.utc),
        purge_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        purge_end=datetime(2026, 1, 6, tzinfo=timezone.utc),
        test_start=datetime(2026, 1, 6, tzinfo=timezone.utc),
        test_end=datetime(2026, 1, 7, tzinfo=timezone.utc),
        model_mae=0.1,
        model_rmse=0.2,
        model_smape=0.3,
        model_mase=0.4,
        model_da=0.5,
        model_f1=0.6,
        model_oos_r2=-0.1,
        naive0_mae=0.11,
        naive0_rmse=0.21,
        naive0_smape=0.31,
        naive0_mase=0.41,
        naive0_da=0.51,
        naive0_f1=0.61,
        naive0_oos_r2=0.01,
        dm_statistic=-3.1,
        dm_pvalue=0.01,
        dm_verdict=dm_verdict,
    )


def test_contains_banned_term_detects_each_fixed_term():
    for term in ("signal", "buy", "sell", "profit", "trade", "recommendation"):
        assert contains_banned_term(f"This is a {term} you should consider.") == term


def test_contains_banned_term_is_case_insensitive():
    assert contains_banned_term("Do not BUY based on this.") == "buy"


def test_contains_banned_term_returns_none_for_clean_text():
    assert contains_banned_term("The model did not beat naive on any split.") is None


def test_directionally_consistent_true_when_no_beat_claim_made():
    run = _make_run()
    splits = [_make_split("worse")]
    text = "The model did not beat naive on the split evaluated."

    assert is_directionally_consistent(text, run, splits) is True


def test_directionally_consistent_true_when_claim_matches_real_better_verdict():
    run = _make_run()
    splits = [_make_split("better")]
    text = "The model beat naive on the split evaluated."

    assert is_directionally_consistent(text, run, splits) is True


def test_directionally_consistent_false_when_claim_contradicts_real_verdicts():
    run = _make_run()
    splits = [_make_split("worse")]
    text = "The model beat naive on the split evaluated, showing strong performance."

    assert is_directionally_consistent(text, run, splits) is False


def test_directionally_consistent_true_for_naive_beat_model_claim():
    run = _make_run()
    splits = [_make_split("worse")]
    text = "Naive0 outperformed the model on the split evaluated."

    assert is_directionally_consistent(text, run, splits) is True
