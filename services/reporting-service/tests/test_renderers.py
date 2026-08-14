"""RS-003 tests: `ReportRenderer`/`get_report_renderer` Factory and
`ValidationAuditRenderer`.

Extra-scrutiny checks (ticket RS-003 Test acceptance criteria): the mandatory
statistical-accuracy-vs-economic-value disclaimer must be present verbatim in
every rendered report (completed/mixed, all-worse, and status-only), a
did-not-beat-naive outcome must render plainly, and the Factory must raise a
typed error for an unknown report kind rather than fail silently.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

from app.renderers.factory import UnknownReportKindError, get_report_renderer
from app.renderers.validation_audit import ValidationAuditRenderer

DISCLAIMER_TEXT = (
    "This audit evaluates statistical forecast accuracy only. No transaction costs, "
    "slippage, execution, or position sizing were modeled unless the client separately "
    "commissioned the economic module (Subsystem 5). A model that beats naive statistically "
    "may still be unprofitable after costs, and vice versa is not implied either."
)


def _make_run(status: str = "completed", failure_reason: str | None = None) -> RunDetailResponse:
    return RunDetailResponse(
        id="run-1",
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=24,
        purge_gap_hours=24,
        split_config={},
        status=status,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=(
            datetime(2026, 1, 2, tzinfo=timezone.utc) if status == "completed" else None
        ),
        failure_reason=failure_reason,
    )


def _make_split(index: int, dm_verdict: str, dm_statistic: float, dm_pvalue: float) -> SplitResultResponse:
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
        dm_statistic=dm_statistic,
        dm_pvalue=dm_pvalue,
        dm_verdict=dm_verdict,
    )


def test_get_report_renderer_returns_validation_audit_renderer():
    renderer = get_report_renderer("validation_audit")
    assert isinstance(renderer, ValidationAuditRenderer)


def test_get_report_renderer_raises_typed_error_for_unknown_kind():
    with pytest.raises(UnknownReportKindError):
        get_report_renderer("nonexistent_kind")


def test_completed_run_with_mixed_verdicts_renders_table_verdict_and_disclaimer():
    run = _make_run(status="completed")
    splits = [
        _make_split(0, "better", -3.1, 0.01),
        _make_split(1, "worse", 2.8, 0.02),
        _make_split(2, "no significant difference", 0.5, 0.6),
    ]

    html = ValidationAuditRenderer().render(run, splits)

    assert "run-1" in html
    assert "Results table" in html
    assert "dataset-1" in html
    # DM fields rendered verbatim, unmodified.
    assert "-3.1" in html
    assert "2.8" in html
    assert "0.01" in html
    assert "better" in html
    assert "worse" in html
    assert "no significant difference" in html
    assert "mixed across splits" in html
    assert DISCLAIMER_TEXT in html


def test_run_that_never_beats_naive_renders_did_not_beat_naive_plainly():
    run = _make_run(status="completed")
    splits = [
        _make_split(0, "worse", 2.8, 0.02),
        _make_split(1, "worse", 3.1, 0.01),
    ]

    html = ValidationAuditRenderer().render(run, splits)

    assert "did not beat naive" in html
    assert "0 better, 2 worse" in html
    assert DISCLAIMER_TEXT in html


def test_failed_run_with_no_splits_renders_status_only_report_without_error():
    run = _make_run(status="failed", failure_reason="dataset unreachable")

    html = ValidationAuditRenderer().render(run, [])

    assert "failed" in html
    assert "dataset unreachable" in html
    assert "has not completed" in html
    assert "Results table" not in html
    assert DISCLAIMER_TEXT in html


def test_running_run_with_no_splits_renders_status_only_report():
    run = _make_run(status="running")

    html = ValidationAuditRenderer().render(run, [])

    assert "running" in html
    assert "has not completed" in html
    assert DISCLAIMER_TEXT in html
