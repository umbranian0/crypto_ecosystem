"""RS-004: `POST /reports/generate`.

Fakes `validation-service` with `httpx.MockTransport` (ticket Test AC1,
mirrors gateway-api's GW-008/GW-009 own test precedent), and an in-memory
fake `ReportRepository` (RS-005's own `test_get_report_endpoint.py`
precedent) rather than real Postgres -- `ReportRepository` is a
`typing.Protocol` with no `sqlalchemy` import, so a plain dataclass-backed
fake satisfies it fully.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.http_client import get_validation_service_client
from app.dependencies.repositories import get_report_repository
from app.repositories.interfaces import ReportRecord
from app.routers import report_generation

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"

RUN_OWNED_BY_A = "run-owned-by-a"
RUN_OWNED_BY_B = "run-owned-by-b"
RUN_FAILED = "run-failed"

_SEED_RUNS: dict[str, dict] = {
    RUN_OWNED_BY_A: {
        "id": RUN_OWNED_BY_A,
        "tenant_id": TENANT_A,
        "dataset_id": "dataset-a",
        "horizon": 5,
        "purge_gap_hours": 2.0,
        "split_config": {"train_window": 30, "test_window": 7, "step": 7},
        "status": "completed",
        "created_at": "2026-01-01T00:00:00",
        "completed_at": "2026-01-01T00:05:00",
        "failure_reason": None,
    },
    RUN_OWNED_BY_B: {
        "id": RUN_OWNED_BY_B,
        "tenant_id": TENANT_B,
        "dataset_id": "dataset-b",
        "horizon": 3,
        "purge_gap_hours": 1.0,
        "split_config": {"train_window": 20, "test_window": 5, "step": 5},
        "status": "completed",
        "created_at": "2026-01-02T00:00:00",
        "completed_at": "2026-01-02T00:05:00",
        "failure_reason": None,
    },
    RUN_FAILED: {
        "id": RUN_FAILED,
        "tenant_id": TENANT_A,
        "dataset_id": "dataset-a",
        "horizon": 5,
        "purge_gap_hours": 2.0,
        "split_config": {"train_window": 30, "test_window": 7, "step": 7},
        "status": "failed",
        "created_at": "2026-01-01T00:00:00",
        "completed_at": None,
        "failure_reason": "dataset unreachable",
    },
}

_SPLIT_RECORD = {
    "split_index": 0,
    "train_start": "2026-01-01T00:00:00",
    "train_end": "2026-01-08T00:00:00",
    "purge_start": "2026-01-08T00:00:00",
    "purge_end": "2026-01-08T02:00:00",
    "test_start": "2026-01-08T02:00:00",
    "test_end": "2026-01-15T02:00:00",
    "model_mae": 1.1,
    "model_rmse": 1.2,
    "model_smape": 1.3,
    "model_mase": 1.4,
    "model_da": 0.5,
    "model_f1": 0.6,
    "model_oos_r2": 0.7,
    "naive0_mae": 2.1,
    "naive0_rmse": 2.2,
    "naive0_smape": 2.3,
    "naive0_mase": 2.4,
    "naive0_da": 0.4,
    "naive0_f1": 0.3,
    "naive0_oos_r2": 0.2,
    "dm_statistic": 3.1,
    "dm_pvalue": 0.02,
    "dm_verdict": "model_better",
}

_SEED_SPLITS: dict[str, list[dict]] = {
    RUN_OWNED_BY_A: [_SPLIT_RECORD],
    RUN_FAILED: [],
}


@dataclass
class FakeValidationService:
    """Records every request it handles (proves `X-Tenant-Id` is forwarded),
    and mimics validation-service's real 404-collapses-both-cases tenant-
    ownership rule (VS-007/VS-008), same as gateway-api's own
    `test_runs_routing.py::FakeValidationService`.
    """

    seen_requests: list[httpx.Request] = field(default_factory=list)
    fail_mode: str | None = None  # None | "connect" | "timeout"

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen_requests.append(request)
        if self.fail_mode == "connect":
            raise httpx.ConnectError("connection refused", request=request)
        if self.fail_mode == "timeout":
            raise httpx.TimeoutException("timed out", request=request)

        tenant_id = request.headers.get("x-tenant-id")
        path = request.url.path

        if request.method == "GET" and path.endswith("/splits"):
            run_id = path.removeprefix("/runs/").removesuffix("/splits")
            run = _SEED_RUNS.get(run_id)
            if run is None or run["tenant_id"] != tenant_id:
                return httpx.Response(404, json={"detail": "run not found"})
            return httpx.Response(200, json=_SEED_SPLITS.get(run_id, []))

        if request.method == "GET":
            run_id = path.removeprefix("/runs/")
            run = _SEED_RUNS.get(run_id)
            if run is None or run["tenant_id"] != tenant_id:
                return httpx.Response(404, json={"detail": "run not found"})
            return httpx.Response(200, json=run)

        raise AssertionError(f"unexpected request: {request.method} {path}")  # pragma: no cover


@dataclass
class FakeReportRepository:
    created: list[ReportRecord] = field(default_factory=list)

    def create_report(
        self, tenant_id: str, run_id: str, report_kind: str, content: str, status: str
    ) -> ReportRecord:
        record = ReportRecord(
            id=f"report-{len(self.created)}",
            tenant_id=tenant_id,
            run_id=run_id,
            report_kind=report_kind,
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            content=content,
            status=status,
        )
        self.created.append(record)
        return record

    def get_report(self, tenant_id: str, report_id: str) -> ReportRecord | None:  # pragma: no cover
        raise NotImplementedError


@pytest.fixture()
def fake_validation_service() -> FakeValidationService:
    return FakeValidationService()


@pytest.fixture()
def fake_repository() -> FakeReportRepository:
    return FakeReportRepository()


@pytest.fixture()
def client(
    fake_validation_service: FakeValidationService, fake_repository: FakeReportRepository
) -> TestClient:
    app = FastAPI()
    app.include_router(report_generation.router, prefix="/reports")

    mock_client = httpx.Client(
        transport=httpx.MockTransport(fake_validation_service.handler),
        base_url="http://validation-service",
    )

    app.dependency_overrides[get_validation_service_client] = lambda: mock_client
    app.dependency_overrides[get_report_repository] = lambda: fake_repository

    return TestClient(app)


def test_generate_report_success_renders_and_persists(
    client: TestClient, fake_repository: FakeReportRepository
) -> None:
    response = client.post(
        "/reports/generate",
        json={"run_id": RUN_OWNED_BY_A},
        headers={"X-Tenant-Id": TENANT_A},
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"id", "status"}
    assert body["status"] == "generated"

    assert len(fake_repository.created) == 1
    persisted = fake_repository.created[0]
    assert persisted.tenant_id == TENANT_A
    assert persisted.run_id == RUN_OWNED_BY_A
    assert persisted.report_kind == "validation_audit"
    assert "dataset-a" in persisted.content


def test_generate_report_outbound_request_carries_resolved_tenant_id(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    client.post(
        "/reports/generate",
        json={"run_id": RUN_OWNED_BY_A},
        headers={"X-Tenant-Id": TENANT_A},
    )

    assert len(fake_validation_service.seen_requests) == 2
    for seen in fake_validation_service.seen_requests:
        assert seen.headers["x-tenant-id"] == TENANT_A


def test_generate_report_for_nonexistent_run_returns_404(client: TestClient) -> None:
    response = client.post(
        "/reports/generate",
        json={"run_id": "does-not-exist"},
        headers={"X-Tenant-Id": TENANT_A},
    )

    assert response.status_code == 404


def test_generate_report_for_cross_tenant_run_returns_404(client: TestClient) -> None:
    """Tenant A requesting a run owned by tenant B -- validation-service's
    own 404 (VS-007/VS-008) passes through as this endpoint's own 404, no
    distinction from the nonexistent-run case (ticket Design section).
    """
    response = client.post(
        "/reports/generate",
        json={"run_id": RUN_OWNED_BY_B},
        headers={"X-Tenant-Id": TENANT_A},
    )

    assert response.status_code == 404


def test_generate_report_connection_failure_returns_502_with_no_leaked_detail(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    fake_validation_service.fail_mode = "connect"

    response = client.post(
        "/reports/generate",
        json={"run_id": RUN_OWNED_BY_A},
        headers={"X-Tenant-Id": TENANT_A},
    )

    assert response.status_code == 502
    detail = response.json()["detail"]
    assert "validation-service" not in detail
    assert "http://" not in detail


def test_generate_report_timeout_returns_504_with_no_leaked_detail(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    fake_validation_service.fail_mode = "timeout"

    response = client.post(
        "/reports/generate",
        json={"run_id": RUN_OWNED_BY_A},
        headers={"X-Tenant-Id": TENANT_A},
    )

    assert response.status_code == 504
    detail = response.json()["detail"]
    assert "validation-service" not in detail
    assert "http://" not in detail


def test_generate_report_for_failed_run_still_generates_status_only_report(
    client: TestClient, fake_repository: FakeReportRepository
) -> None:
    response = client.post(
        "/reports/generate",
        json={"run_id": RUN_FAILED},
        headers={"X-Tenant-Id": TENANT_A},
    )

    assert response.status_code == 201
    assert len(fake_repository.created) == 1
    persisted = fake_repository.created[0]
    assert "failed" in persisted.content
    assert "dataset unreachable" in persisted.content
    assert "has not completed" in persisted.content


def test_generate_report_missing_tenant_header_returns_401_before_any_downstream_call(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.post("/reports/generate", json={"run_id": RUN_OWNED_BY_A})

    assert response.status_code == 401
    assert fake_validation_service.seen_requests == []
