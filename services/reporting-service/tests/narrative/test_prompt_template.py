"""AI-002 tests: `app.narrative.prompt_template.build_prompt`."""

from __future__ import annotations

from datetime import datetime, timezone

from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

from app.narrative.prompt_template import PROMPT_TEMPLATE_VERSION, build_prompt


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


def _make_split(index: int, dm_verdict: str) -> SplitResultResponse:
    return SplitResultResponse(
        split_index=index,
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


def test_prompt_version_is_pinned():
    assert PROMPT_TEMPLATE_VERSION


def test_build_prompt_includes_run_and_split_fields_only():
    run = _make_run()
    splits = [_make_split(0, "better"), _make_split(1, "worse")]

    prompt = build_prompt(run, splits)

    assert "run-1" in prompt
    assert "dataset-1" in prompt
    assert "24" in prompt  # horizon / purge gap
    assert "better" in prompt
    assert "worse" in prompt
    assert "1 better, 1 worse, 0 no significant difference" in prompt


def test_build_prompt_instructs_the_model_to_avoid_banned_terms_and_fabrication():
    prompt = build_prompt(_make_run(), [])

    assert "signal" in prompt.lower()
    assert "buy" in prompt.lower()
    assert "invent" in prompt.lower()
    assert "forecast" in prompt.lower()
