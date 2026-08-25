"""VS-017: `POST /runs` client-supplied prediction baseline tests.

New file (not appended to test_runs_endpoint.py) per this ticket's own file
scope: `runs.py` is this ticket's only touched router, but keeping the
client-baseline-specific scenarios in their own file avoids growing an
already-large existing file and makes the regression proof below easy to
audit on its own.
"""

from __future__ import annotations

from datetime import datetime, timedelta

from fastapi.testclient import TestClient

from app.client_baseline import CLIENT_PREDICTION_AUDIT_DISCLAIMER

VALID_CONFIG = {
    "horizon": 1,
    "purge_gap_hours": 0,
    "train_window": 10,
    "test_window": 5,
    "step": 5,
}


def _inline_dataset(n: int = 40, offset: float = 0.0) -> dict:
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = [float(i) + offset for i in range(n)]
    return {"inline": {"timestamps": timestamps, "values": values}}


def _client_prediction_dataset(n: int = 40) -> dict:
    # A distinct-from-Naive0/NaiveLast prediction series (constant 42.0),
    # covering every timestamp of the primary dataset so every split's
    # test.index is fully covered -- ClientPredictionBaseline.predict must
    # never need to raise here.
    start = datetime(2024, 1, 1)
    timestamps = [(start + timedelta(hours=i)).isoformat() for i in range(n)]
    values = [42.0 for _ in range(n)]
    return {"inline": {"timestamps": timestamps, "values": values}}


def _client(tmp_path, monkeypatch) -> tuple[TestClient, str]:
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("VALIDATION_SERVICE_DB_PATH", db_path)
    from app.main import app

    return TestClient(app), db_path


def test_post_runs_with_client_prediction_persists_non_null_client_baseline_results(
    tmp_path, monkeypatch
):
    client, db_path = _client(tmp_path, monkeypatch)
    from app.repositories.sqlite_repository import SQLiteSplitResultRepository

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "client_prediction_reference": _client_prediction_dataset(),
        **VALID_CONFIG,
    }

    response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response.status_code == 201, response.text
    run_id = response.json()["id"]
    assert response.json()["status"] == "completed"

    split_repo = SQLiteSplitResultRepository(db_path)
    persisted = split_repo.get_splits("tenant-1", run_id)
    assert len(persisted) > 0

    for split in persisted:
        assert split.client_baseline_results is not None
        assert split.client_baseline_results["key"] == "ClientPredictionBaseline"
        assert set(split.client_baseline_results["metrics"].keys()) == {
            "mae", "rmse", "smape", "mase", "da", "f1", "oos_r2",
        }
        assert "dm_statistic" in split.client_baseline_results
        assert "dm_pvalue" in split.client_baseline_results
        assert "dm_verdict" in split.client_baseline_results


def test_client_prediction_does_not_perturb_mandatory_naive_baselines(tmp_path, monkeypatch):
    """Same dataset/config, one request with a client_prediction_reference and
    one without -- the persisted naive0_*/model_* (naive_last) fields must be
    identical in shape and value either way, proving the third baseline
    doesn't perturb the two mandatory ones' computed values.
    """
    client, db_path = _client(tmp_path, monkeypatch)
    from app.repositories.sqlite_repository import SQLiteSplitResultRepository

    base_payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }

    without_client = client.post(
        "/runs", json=base_payload, headers={"X-Tenant-Id": "tenant-1"}
    )
    assert without_client.status_code == 201, without_client.text
    run_id_without = without_client.json()["id"]

    with_client_payload = {
        **base_payload,
        "client_prediction_reference": _client_prediction_dataset(),
    }
    with_client = client.post(
        "/runs", json=with_client_payload, headers={"X-Tenant-Id": "tenant-1"}
    )
    assert with_client.status_code == 201, with_client.text
    run_id_with = with_client.json()["id"]

    split_repo = SQLiteSplitResultRepository(db_path)
    splits_without = split_repo.get_splits("tenant-1", run_id_without)
    splits_with = split_repo.get_splits("tenant-1", run_id_with)

    assert len(splits_without) == len(splits_with)

    naive_fields = [
        "model_mae", "model_rmse", "model_smape", "model_mase", "model_da", "model_f1", "model_oos_r2",
        "naive0_mae", "naive0_rmse", "naive0_smape", "naive0_mase", "naive0_da", "naive0_f1", "naive0_oos_r2",
        "dm_statistic", "dm_pvalue", "dm_verdict",
    ]
    for split_without, split_with in zip(splits_without, splits_with):
        for field in naive_fields:
            assert getattr(split_without, field) == getattr(split_with, field), field

    assert all(s.client_baseline_results is None for s in splits_without)
    assert all(s.client_baseline_results is not None for s in splits_with)


def test_post_runs_without_client_prediction_reference_leaves_client_baseline_results_null(
    tmp_path, monkeypatch
):
    """Regression proof (not just 'the field is optional in the type'): a
    request with no `client_prediction_reference` at all persists every
    split with `client_baseline_results = NULL`, matching pre-ticket
    behavior. Running the identical request twice (two runs) produces
    identical naive0_*/model_*/dm_* values across both runs, confirming this
    code path is unaffected by VS-017's new branch.
    """
    client, db_path = _client(tmp_path, monkeypatch)
    from app.repositories.sqlite_repository import SQLiteSplitResultRepository

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }

    response_1 = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    response_2 = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert response_1.status_code == 201, response_1.text
    assert response_2.status_code == 201, response_2.text

    split_repo = SQLiteSplitResultRepository(db_path)
    splits_1 = split_repo.get_splits("tenant-1", response_1.json()["id"])
    splits_2 = split_repo.get_splits("tenant-1", response_2.json()["id"])

    assert len(splits_1) == len(splits_2) > 0

    all_fields = [
        "split_index", "train_start", "train_end", "purge_start", "purge_end", "test_start", "test_end",
        "model_mae", "model_rmse", "model_smape", "model_mase", "model_da", "model_f1", "model_oos_r2",
        "naive0_mae", "naive0_rmse", "naive0_smape", "naive0_mase", "naive0_da", "naive0_f1", "naive0_oos_r2",
        "dm_statistic", "dm_pvalue", "dm_verdict", "client_baseline_results",
    ]
    for s1, s2 in zip(splits_1, splits_2):
        for field in all_fields:
            assert getattr(s1, field) == getattr(s2, field), field

    assert all(s.client_baseline_results is None for s in splits_1)
    assert all(s.client_baseline_results is None for s in splits_2)


def test_get_splits_includes_disclaimer_verbatim_when_client_baseline_present(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        "client_prediction_reference": _client_prediction_dataset(),
        **VALID_CONFIG,
    }
    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert create_response.status_code == 201, create_response.text
    run_id = create_response.json()["id"]

    splits_response = client.get(f"/runs/{run_id}/splits", headers={"X-Tenant-Id": "tenant-1"})
    assert splits_response.status_code == 200, splits_response.text

    # Substring match against the RAW response body, not just "the field
    # exists" -- this is what proves the disclaimer is on the actual wire
    # response, not only a Python constant unused by any response path.
    assert CLIENT_PREDICTION_AUDIT_DISCLAIMER in splits_response.text

    body = splits_response.json()
    assert len(body) > 0
    for row in body:
        assert row["client_baseline"] is not None
        assert row["client_baseline"]["disclaimer"] == CLIENT_PREDICTION_AUDIT_DISCLAIMER
        assert row["client_baseline"]["key"] == "ClientPredictionBaseline"


def test_get_splits_client_baseline_is_null_when_not_supplied(tmp_path, monkeypatch):
    client, _ = _client(tmp_path, monkeypatch)

    payload = {
        "dataset_id": "dataset-1",
        "dataset_reference": _inline_dataset(),
        **VALID_CONFIG,
    }
    create_response = client.post("/runs", json=payload, headers={"X-Tenant-Id": "tenant-1"})
    assert create_response.status_code == 201, create_response.text
    run_id = create_response.json()["id"]

    splits_response = client.get(f"/runs/{run_id}/splits", headers={"X-Tenant-Id": "tenant-1"})
    assert splits_response.status_code == 200, splits_response.text

    body = splits_response.json()
    assert len(body) > 0
    for row in body:
        assert row["client_baseline"] is None

    assert CLIENT_PREDICTION_AUDIT_DISCLAIMER not in splits_response.text
