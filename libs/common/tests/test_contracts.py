from __future__ import annotations

from datetime import datetime

import pytest
from pydantic import ValidationError

from naive_first_common.contracts import (
    InlineDatasetReference,
    ObjectKeyDatasetReference,
    PathDatasetReference,
    RunDetailResponse,
    RunRequest,
    RunResponse,
    RunSummaryResponse,
    SplitResultResponse,
    StoredDatasetReference,
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


def test_run_request_accepts_all_three_dataset_reference_shapes_unchanged() -> None:
    # UAT-007: dataset_reference's runtime type stays plain dict -- any shape
    # previously accepted must still construct without error.
    for reference in (
        {"path": "/data/btc_1h.csv"},
        {"inline": {"timestamps": ["2026-01-01T00:00:00"], "values": [1.0]}},
        {"source": "binance_btcusdt_1h", "start": "2026-01-01T00:00:00", "field": "close"},
        {"object_key": "processed/tenant-1/dataset-1.csv"},
    ):
        request = RunRequest(
            dataset_id="dataset-1",
            dataset_reference=reference,
            horizon=1,
            purge_gap_hours=0,
            train_window=30,
            test_window=7,
            step=7,
        )
        assert request.dataset_reference == reference


def test_run_request_label_defaults_to_none() -> None:
    request = RunRequest(
        dataset_id="dataset-1",
        dataset_reference={"path": "/data/btc_1h.csv"},
        horizon=1,
        purge_gap_hours=0,
        train_window=30,
        test_window=7,
        step=7,
    )
    assert request.label is None


def test_run_request_label_accepts_a_freeform_string() -> None:
    request = RunRequest(
        dataset_id="dataset-1",
        dataset_reference={"path": "/data/btc_1h.csv"},
        horizon=1,
        purge_gap_hours=0,
        train_window=30,
        test_window=7,
        step=7,
        label="weekly audit",
    )
    assert request.label == "weekly audit"


def test_run_request_label_over_200_chars_rejected() -> None:
    with pytest.raises(ValidationError):
        RunRequest(
            dataset_id="dataset-1",
            dataset_reference={"path": "/data/btc_1h.csv"},
            horizon=1,
            purge_gap_hours=0,
            train_window=30,
            test_window=7,
            step=7,
            label="x" * 201,
        )


def test_run_summary_response_label_defaults_to_none() -> None:
    summary = RunSummaryResponse(
        id="run-1",
        dataset_id="dataset-1",
        horizon=1,
        status="completed",
        created_at=datetime(2026, 1, 1),
        completed_at=None,
    )
    assert summary.label is None


def test_run_request_dataset_reference_schema_has_no_bare_additional_properties() -> None:
    schema = RunRequest.model_json_schema()
    dataset_reference_schema = schema["properties"]["dataset_reference"]

    assert dataset_reference_schema != {"additionalProperties": True, "title": "Dataset Reference", "type": "object"}
    assert "anyOf" in dataset_reference_schema

    titles = {shape["title"] for shape in dataset_reference_schema["anyOf"]}
    assert titles == {
        "PathDatasetReference",
        "InlineDatasetReference",
        "StoredDatasetReference",
        "ObjectKeyDatasetReference",
    }
    for shape in dataset_reference_schema["anyOf"]:
        required_field = shape["required"][0]
        assert "examples" in shape["properties"][required_field]


def test_dataset_reference_shape_models_have_examples() -> None:
    for model in (
        PathDatasetReference,
        InlineDatasetReference,
        StoredDatasetReference,
        ObjectKeyDatasetReference,
    ):
        shape_schema = model.model_json_schema()
        required_field = shape_schema["required"][0]
        assert "examples" in shape_schema["properties"][required_field]


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
