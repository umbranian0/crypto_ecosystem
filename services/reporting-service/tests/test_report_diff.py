"""RPT-004-01: `app.diff` unit tests and `GET /reports/{id}/diff/{other_id}`."""

from __future__ import annotations

import copy
import json
import re
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

from app import diff
from app.dependencies.http_client import get_validation_service_client
from app.dependencies.repositories import get_report_repository
from app.repositories.interfaces import ReportRecord
from app.routers import report_diff

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"

_RUN = {
    "tenant_id": TENANT_A,
    "dataset_id": "dataset-a",
    "horizon": 5,
    "purge_gap_hours": 2.0,
    "split_config": {"train_window": 30, "test_window": 7, "step": 7},
    "status": "completed",
    "created_at": "2026-01-01T00:00:00",
    "completed_at": "2026-01-01T00:05:00",
    "failure_reason": None,
}


def _run(run_id: str, **overrides) -> dict:
    return {**copy.deepcopy(_RUN), "id": run_id, **overrides}


def _split(index: int = 0, **overrides) -> dict:
    base = {
        "split_index": index,
        "train_start": "2026-01-01T00:00:00",
        "train_end": "2026-01-08T00:00:00",
        "purge_start": "2026-01-08T00:00:00",
        "purge_end": "2026-01-08T02:00:00",
        "test_start": f"2026-01-{8 + index:02d}T02:00:00",
        "test_end": f"2026-01-{15 + index:02d}T02:00:00",
        "dm_statistic": 3.1,
        "dm_pvalue": 0.02,
        "dm_verdict": "model_better",
    }
    for m in diff._METRICS:
        base[f"model_{m}"] = 1.0
        base[f"naive0_{m}"] = 2.0
    return {**base, **overrides}


def _split_model(index: int = 0, **overrides) -> SplitResultResponse:
    return SplitResultResponse(**_split(index, **overrides))


def _run_model(run_id: str = "r", **overrides) -> RunDetailResponse:
    return RunDetailResponse(**_run(run_id, **overrides))


# ---------------------------------------------------------------- unit tests


def test_delta_is_other_minus_base() -> None:
    out = diff.diff_splits([_split_model(model_mae=1.0)], [_split_model(model_mae=1.75)])
    assert out[0].metrics["model_mae"].base == 1.0
    assert out[0].metrics["model_mae"].other == 1.75
    assert out[0].metrics["model_mae"].delta == 0.75
    assert out[0].metrics["naive0_mae"].delta == 0.0


def test_fields_are_exactly_the_documented_set() -> None:
    out = diff.diff_splits([_split_model()], [_split_model()])
    expected = (
        {f"model_{m}" for m in diff._METRICS}
        | {f"naive0_{m}" for m in diff._METRICS}
        | {"dm_statistic", "dm_pvalue"}
    )
    assert set(out[0].metrics) == expected


def test_none_on_either_side_gives_null_delta() -> None:
    undefined = _split_model(dm_statistic=None, dm_pvalue=None)
    out = diff.diff_splits([undefined], [_split_model()])
    assert out[0].metrics["dm_statistic"].delta is None
    assert out[0].metrics["dm_statistic"].base is None
    assert out[0].metrics["dm_statistic"].other == 3.1
    out = diff.diff_splits([_split_model()], [undefined])
    assert out[0].metrics["dm_pvalue"].delta is None


def test_verdict_changed_and_unchanged() -> None:
    same = diff.diff_splits([_split_model()], [_split_model()])
    assert same[0].dm_verdict.changed is False
    changed = diff.diff_splits(
        [_split_model()], [_split_model(dm_verdict="no_significant_difference")]
    )
    assert changed[0].dm_verdict.changed is True
    assert changed[0].dm_verdict.base == "model_better"


def test_undefined_is_not_conflated_with_no_significant_difference() -> None:
    undefined = _split_model(
        dm_statistic=None, dm_pvalue=None, dm_verdict="no_significant_difference"
    )
    plain = _split_model(dm_verdict="no_significant_difference")
    out = diff.diff_splits([undefined], [plain])
    assert out[0].dm_verdict.changed is True


def test_splits_ordered_by_split_index() -> None:
    base = [_split_model(2), _split_model(0), _split_model(1)]
    other = [_split_model(1), _split_model(2), _split_model(0)]
    assert [s.split_index for s in diff.diff_splits(base, other)] == [0, 1, 2]


def test_self_diff_has_zero_deltas_and_no_changes() -> None:
    splits = [_split_model(0), _split_model(1, dm_statistic=None, dm_pvalue=None)]
    out = diff.diff_splits(splits, splits)
    assert all(not s.dm_verdict.changed for s in out)
    for s in out:
        for f in s.metrics.values():
            assert f.delta in (0.0, None)


def test_comparability_failure_reasons_in_order() -> None:
    base = _run_model()
    assert diff.comparability_failure(base, _run_model()) is None
    assert "datasets" in diff.comparability_failure(base, _run_model(dataset_id="x"))
    assert "horizons" in diff.comparability_failure(base, _run_model(horizon=9))
    assert "split configurations" in diff.comparability_failure(
        base, _run_model(purge_gap_hours=3.0)
    )
    assert "split configurations" in diff.comparability_failure(
        base, _run_model(split_config={"step": 1})
    )


def test_alignment_failure() -> None:
    a = [_split_model(0), _split_model(1)]
    assert diff.alignment_failure(a, [_split_model(1), _split_model(0)]) is None
    assert "split sets" in diff.alignment_failure(a, [_split_model(0)])
    shifted = [_split_model(0), _split_model(1, test_end="2026-03-01T00:00:00")]
    assert "test windows" in diff.alignment_failure(a, shifted)


# ------------------------------------------------------------ endpoint tests


@dataclass
class FakeValidationService:
    runs: dict[str, dict] = field(default_factory=dict)
    splits: dict[str, list[dict]] = field(default_factory=dict)
    counts: dict[str, int] = field(default_factory=dict)
    seen: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen.append(request)
        tenant = request.headers.get("x-tenant-id")
        parts = request.url.path.strip("/").split("/")
        run = self.runs.get(parts[1])
        if run is None or run["tenant_id"] != tenant:
            return httpx.Response(404, json={"detail": "run not found"})
        if len(parts) == 2:
            return httpx.Response(200, json=run)
        if parts[2:] == ["splits", "count"]:
            total = self.counts.get(parts[1], len(self.splits.get(parts[1], [])))
            return httpx.Response(200, json={"total": total})
        if parts[2:] == ["splits"]:
            return httpx.Response(200, json=self.splits.get(parts[1], []))
        raise AssertionError(request.url.path)  # pragma: no cover


@dataclass
class FakeRepo:
    records: dict[str, ReportRecord] = field(default_factory=dict)

    def add(self, report_id: str, run_id: str, tenant: str = TENANT_A, kind: str = "validation_audit"):
        self.records[report_id] = ReportRecord(
            id=report_id,
            tenant_id=tenant,
            run_id=run_id,
            report_kind=kind,
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            content="<html></html>",
            status="generated",
        )

    def create_report(self, *a, **k):  # pragma: no cover
        raise NotImplementedError

    def get_report(self, tenant_id: str, report_id: str) -> ReportRecord | None:
        rec = self.records.get(report_id)
        return rec if rec is not None and rec.tenant_id == tenant_id else None


@pytest.fixture()
def world() -> tuple[FakeValidationService, FakeRepo]:
    vs = FakeValidationService()
    repo = FakeRepo()
    vs.runs["run-1"] = _run("run-1")
    vs.runs["run-2"] = _run("run-2")
    vs.splits["run-1"] = [_split(0), _split(1)]
    vs.splits["run-2"] = [_split(0, model_mae=1.5), _split(1, dm_verdict="no_significant_difference")]
    repo.add("rep-1", "run-1")
    repo.add("rep-2", "run-2")
    return vs, repo


@pytest.fixture()
def client(world) -> TestClient:
    vs, repo = world
    app = FastAPI()
    app.include_router(report_diff.router, prefix="/reports")
    mock = httpx.Client(transport=httpx.MockTransport(vs.handler), base_url="http://validation-service")
    app.dependency_overrides[get_validation_service_client] = lambda: mock
    app.dependency_overrides[get_report_repository] = lambda: repo
    return TestClient(app)


def _get(client: TestClient, a: str, b: str, tenant: str = TENANT_A):
    return client.get(f"/reports/{a}/diff/{b}", headers={"X-Tenant-Id": tenant})


def test_happy_path(client: TestClient, world) -> None:
    vs, _ = world
    response = _get(client, "rep-1", "rep-2")
    assert response.status_code == 200
    body = response.json()
    assert set(body) == {
        "report_id", "other_report_id", "run_id", "other_run_id", "dataset_id",
        "horizon", "split_count", "verdict_changed_split_count", "splits",
    }
    assert body["report_id"] == "rep-1" and body["other_report_id"] == "rep-2"
    assert body["run_id"] == "run-1" and body["other_run_id"] == "run-2"
    assert body["dataset_id"] == "dataset-a" and body["horizon"] == 5
    assert body["split_count"] == 2
    assert body["verdict_changed_split_count"] == 1
    first, second = body["splits"]
    assert first["split_index"] == 0 and second["split_index"] == 1
    assert first["metrics"]["model_mae"] == {"base": 1.0, "other": 1.5, "delta": 0.5}
    assert first["dm_verdict"]["changed"] is False
    assert second["dm_verdict"] == {
        "base": "model_better", "other": "no_significant_difference", "changed": True,
    }
    assert all(r.headers["x-tenant-id"] == TENANT_A for r in vs.seen)


def test_either_id_position(client: TestClient) -> None:
    forward = _get(client, "rep-1", "rep-2").json()
    reverse = _get(client, "rep-2", "rep-1").json()
    assert reverse["run_id"] == "run-2"
    assert reverse["splits"][0]["metrics"]["model_mae"]["delta"] == -0.5
    assert forward["verdict_changed_split_count"] == reverse["verdict_changed_split_count"] == 1


def test_self_diff_allowed(client: TestClient) -> None:
    body = _get(client, "rep-1", "rep-1").json()
    assert body["verdict_changed_split_count"] == 0
    assert all(f["delta"] == 0.0 for s in body["splits"] for f in s["metrics"].values())


def test_non_audit_kind_rejected(client: TestClient, world) -> None:
    _, repo = world
    repo.add("rep-trend", "consistency_trend:dataset-a:5", kind="consistency_trend")
    response = _get(client, "rep-1", "rep-trend")
    assert response.status_code == 422
    assert response.json()["detail"] == "both reports must be of kind 'validation_audit'"


def test_different_dataset_rejected(client: TestClient, world) -> None:
    vs, _ = world
    vs.runs["run-2"]["dataset_id"] = "dataset-z"
    response = _get(client, "rep-1", "rep-2")
    assert response.status_code == 422
    assert response.json()["detail"] == "runs use different datasets"


def test_different_horizon_rejected(client: TestClient, world) -> None:
    vs, _ = world
    vs.runs["run-2"]["horizon"] = 9
    response = _get(client, "rep-1", "rep-2")
    assert response.status_code == 422
    assert response.json()["detail"] == "runs use different horizons"


def test_different_split_config_rejected(client: TestClient, world) -> None:
    vs, _ = world
    vs.runs["run-2"]["split_config"] = {"train_window": 10, "test_window": 7, "step": 7}
    response = _get(client, "rep-1", "rep-2")
    assert response.status_code == 422
    assert response.json()["detail"] == "runs use different split configurations"


def test_too_many_splits_rejected(client: TestClient, world) -> None:
    vs, _ = world
    vs.counts["run-2"] = 501
    response = _get(client, "rep-1", "rep-2")
    assert response.status_code == 422
    assert response.json()["detail"] == "too many splits to diff"


def test_misaligned_splits_rejected(client: TestClient, world) -> None:
    vs, _ = world
    vs.splits["run-2"] = [_split(0)]
    response = _get(client, "rep-1", "rep-2")
    assert response.status_code == 422
    assert response.json()["detail"] == "runs have different split sets"

    vs.splits["run-2"] = [_split(0), _split(1, test_end="2026-03-01T00:00:00")]
    response = _get(client, "rep-1", "rep-2")
    assert response.status_code == 422
    assert response.json()["detail"] == "runs have different test windows for the same split"


def test_unknown_and_cross_tenant_404_are_identical(client: TestClient, world) -> None:
    _, repo = world
    repo.add("rep-b", "run-b", tenant=TENANT_B)
    unknown = _get(client, "rep-1", "nope")
    cross = _get(client, "rep-1", "rep-b")
    first_unknown = _get(client, "nope", "rep-1")
    assert unknown.status_code == cross.status_code == first_unknown.status_code == 404
    assert unknown.json() == cross.json() == first_unknown.json() == {"detail": "report not found"}


def test_run_no_longer_exists_is_404_run_not_found(client: TestClient, world) -> None:
    vs, _ = world
    del vs.runs["run-2"]
    response = _get(client, "rep-1", "rep-2")
    assert response.status_code == 404
    assert response.json() == {"detail": "run not found"}


def test_positioning_no_outcome_language() -> None:
    root = Path(diff.__file__).parent
    sources = (root / "diff.py").read_text() + (root / "routers" / "report_diff.py").read_text()
    pattern = re.compile(r"improv|better model|predict|signal|profit|alpha|regress", re.I)
    assert pattern.search(sources) is None

    vs = FakeValidationService()
    repo = FakeRepo()
    for rid in ("a", "b"):
        vs.runs[f"run-{rid}"] = _run(f"run-{rid}")
        vs.splits[f"run-{rid}"] = [_split(0)]
        repo.add(f"rep-{rid}", f"run-{rid}")
    app = FastAPI()
    app.include_router(report_diff.router, prefix="/reports")
    mock = httpx.Client(transport=httpx.MockTransport(vs.handler), base_url="http://v")
    app.dependency_overrides[get_validation_service_client] = lambda: mock
    app.dependency_overrides[get_report_repository] = lambda: repo
    response = TestClient(app).get("/reports/rep-a/diff/rep-b", headers={"X-Tenant-Id": TENANT_A})
    keys_and_text = json.dumps(response.json()).replace("model_better", "")
    assert pattern.search(keys_and_text) is None
