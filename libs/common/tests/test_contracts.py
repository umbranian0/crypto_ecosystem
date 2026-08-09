from __future__ import annotations

from datetime import datetime

from naive_first_common.contracts import (
    RunDetailResponse,
    RunRequest,
    RunResponse,
    SplitResultResponse,
)


def test_run_request_constructs_with_representative_values() -> None:
    request = RunRequest(
        dataset_id="dataset-1",
        dataset_reference={"path": "s3://bucket/key.csv"},
        horizon=1,
        purge_gap_hours=0,
        train_window=30,
        test_window=7,
        step=7,
    )
    assert request.dataset_id == "dataset-1"
    assert request.horizon == 1


def test_run_response_constructs_with_representative_values() -> None:
    response = RunResponse(id="run-1", status="completed")
    assert response.id == "run-1"
    assert response.status == "completed"


def test_run_detail_response_constructs_with_representative_values() -> None:
    detail = RunDetailResponse(
        id="run-1",
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=1,
        purge_gap_hours=0.0,
        split_config={"train_window": 30, "test_window": 7, "step": 7},
        status="completed",
        created_at=datetime(2026, 1, 1),
        completed_at=datetime(2026, 1, 2),
        failure_reason=None,
    )
    assert detail.status == "completed"
    assert detail.failure_reason is None


def test_split_result_response_constructs_with_representative_values() -> None:
    split = SplitResultResponse(
        split_index=0,
        train_start=datetime(2026, 1, 1),
        train_end=datetime(2026, 1, 10),
        purge_start=None,
        purge_end=None,
        test_start=datetime(2026, 1, 11),
        test_end=datetime(2026, 1, 18),
        model_mae=1.0,
        model_rmse=1.0,
        model_smape=1.0,
        model_mase=1.0,
        model_da=1.0,
        model_f1=1.0,
        model_oos_r2=1.0,
        naive0_mae=1.0,
        naive0_rmse=1.0,
        naive0_smape=1.0,
        naive0_mase=1.0,
        naive0_da=1.0,
        naive0_f1=1.0,
        naive0_oos_r2=1.0,
        dm_statistic=1.0,
        dm_pvalue=0.05,
        dm_verdict="reject",
    )
    assert split.split_index == 0
    assert split.dm_verdict == "reject"
