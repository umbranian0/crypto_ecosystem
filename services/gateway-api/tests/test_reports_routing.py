"""GW-018: `app.routers.reports` (`POST /reports/generate`, `GET /reports/
{id}`), mirroring `test_runs_routing.py`'s existing pattern (httpx.Client
production code -> `httpx.MockTransport` fake, not `ASGITransport`).

Fakes `reporting-service` with `httpx.MockTransport` whose handler mimics the
real response shapes read directly from
`services/reporting-service/src/app/routers/report_generation.py`/
`report_retrieval.py`, including `get_report`'s 404-collapses-both-cases
tenant-ownership rule (RS-002/RS-005).
"""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.http_client import get_reporting_service_client
from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord
from app.routers import reports

RAW_KEY_A = "tenant-a-raw-key"
TENANT_A = "tenant-a"
RAW_KEY_B = "tenant-b-raw-key"
TENANT_B = "tenant-b"

# Seeded directly into the fake backend, owned by TENANT_B -- used by the
# cross-tenant test to prove TENANT_A can never see it (ticket Test AC2).
REPORT_OWNED_BY_A = "report-owned-by-a"
REPORT_OWNED_BY_B = "report-owned-by-b"

_SEED_REPORTS: dict[str, dict] = {
    REPORT_OWNED_BY_A: {
        "id": REPORT_OWNED_BY_A,
        "tenant_id": TENANT_A,
        "run_id": "run-a",
        "report_kind": "validation_audit",
        "generated_at": "2026-01-01T00:00:00",
        "status": "completed",
        "content": "report content for tenant A",
    },
    REPORT_OWNED_BY_B: {
        "id": REPORT_OWNED_BY_B,
        "tenant_id": TENANT_B,
        "run_id": "run-b",
        "report_kind": "validation_audit",
        "generated_at": "2026-01-02T00:00:00",
        "status": "completed",
        "content": "report content for tenant B",
    },
}


@dataclass
class FakeReportingService:
    """Records every request it handles (proving the outbound call actually
    carries `X-Tenant-Id`), and mimics `reporting-service`'s real generate/
    get behavior, including its 404-collapses-both-cases tenant-ownership
    rule (RS-002/RS-005).
    """

    seen_requests: list[httpx.Request]
    created_reports: dict[str, dict]
    simulate_connect_error: bool = False
    simulate_timeout: bool = False

    def handler(self, request: httpx.Request) -> httpx.Response:
        if self.simulate_connect_error:
            raise httpx.ConnectError("connection refused", request=request)
        if self.simulate_timeout:
            raise httpx.TimeoutException("timed out", request=request)

        self.seen_requests.append(request)
        tenant_id = request.headers.get("x-tenant-id")
        path = request.url.path

        if request.method == "POST" and path == "/reports/generate":
            body = json.loads(request.content)
            run_id = body["run_id"]
            new_id = f"report-created-{len(self.created_reports)}"
            record = {
                "id": new_id,
                "tenant_id": tenant_id,
                "run_id": run_id,
                "report_kind": "validation_audit",
                "generated_at": "2026-01-03T00:00:00",
                "status": "completed",
                "content": f"generated content for {run_id}",
            }
            self.created_reports[new_id] = record
            return httpx.Response(201, json={"id": new_id, "status": "completed"})

        if request.method == "GET" and path.startswith("/reports/"):
            report_id = path.removeprefix("/reports/")
            report = _SEED_REPORTS.get(report_id) or self.created_reports.get(report_id)
            if report is None or report["tenant_id"] != tenant_id:
                return httpx.Response(404, json={"detail": "report not found"})
            return httpx.Response(200, json=report)

        raise AssertionError(f"unexpected request: {request.method} {path}")  # pragma: no cover


@dataclass
class FakeApiKeyRepository:
    records_by_hash: dict[str, ApiKeyRecord]

    def create_key(self, tenant_id: str, key_hash: str) -> ApiKeyRecord:  # pragma: no cover
        raise NotImplementedError

    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        return self.records_by_hash.get(key_hash)

    def revoke_key(self, tenant_id: str, key_id: str) -> None:  # pragma: no cover
        raise NotImplementedError


def _api_key_record(raw_key: str, tenant_id: str) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=f"key-{tenant_id}",
        tenant_id=tenant_id,
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        created_at=datetime.now(timezone.utc),
        revoked_at=None,
    )


@pytest.fixture()
def fake_reporting_service() -> FakeReportingService:
    return FakeReportingService(seen_requests=[], created_reports={})


def _build_client(fake_reporting_service: FakeReportingService) -> TestClient:
    app = FastAPI()
    app.include_router(reports.router)

    key_repo = FakeApiKeyRepository(
        {
            hashlib.sha256(RAW_KEY_A.encode()).hexdigest(): _api_key_record(RAW_KEY_A, TENANT_A),
            hashlib.sha256(RAW_KEY_B.encode()).hexdigest(): _api_key_record(RAW_KEY_B, TENANT_B),
        }
    )
    mock_client = httpx.Client(
        transport=httpx.MockTransport(fake_reporting_service.handler),
        base_url="http://reporting-service",
    )

    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    app.dependency_overrides[get_reporting_service_client] = lambda: mock_client

    return TestClient(app)


@pytest.fixture()
def client(fake_reporting_service: FakeReportingService) -> TestClient:
    return _build_client(fake_reporting_service)


def test_post_reports_generate_forwards_and_returns_response_shape(client: TestClient) -> None:
    response = client.post(
        "/reports/generate",
        json={"run_id": "run-a"},
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 201
    body = response.json()
    assert set(body.keys()) == {"id", "status"}
    assert body["status"] == "completed"


def test_get_report_forwards_and_returns_full_detail_shape(client: TestClient) -> None:
    response = client.get(
        f"/reports/{REPORT_OWNED_BY_A}", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 200
    body = response.json()
    assert set(body.keys()) == {
        "id",
        "run_id",
        "report_kind",
        "generated_at",
        "status",
        "content",
    }
    assert body["id"] == REPORT_OWNED_BY_A
    assert body["run_id"] == "run-a"
    assert body["content"] == "report content for tenant A"


def test_cross_tenant_get_report_returns_404(client: TestClient) -> None:
    """Non-tautological cross-tenant proof (ticket Test AC2): tenant A
    authenticated, requesting a report_id seeded as owned by tenant B -- must
    get the same 404 (with the same detail) a nonexistent report would, with
    no gateway-side branch distinguishing the two cases (none exists in this
    router at all). The positive case above independently proves the owning
    tenant *does* see real content, so this 404 isn't just "everything 404s".
    """
    response = client.get(
        f"/reports/{REPORT_OWNED_BY_B}", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 404
    assert response.json()["detail"] == "report not found"

    nonexistent_response = client.get(
        "/reports/does-not-exist", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )
    assert nonexistent_response.status_code == 404
    assert nonexistent_response.json()["detail"] == response.json()["detail"]


def test_same_report_visible_to_owning_tenant(client: TestClient) -> None:
    response = client.get(
        f"/reports/{REPORT_OWNED_BY_B}", headers={"Authorization": f"Bearer {RAW_KEY_B}"}
    )

    assert response.status_code == 200
    assert response.json()["id"] == REPORT_OWNED_BY_B


def test_outbound_request_carries_authenticated_tenant_x_tenant_id_header(
    client: TestClient, fake_reporting_service: FakeReportingService
) -> None:
    client.get(f"/reports/{REPORT_OWNED_BY_A}", headers={"Authorization": f"Bearer {RAW_KEY_A}"})

    assert len(fake_reporting_service.seen_requests) == 1
    assert fake_reporting_service.seen_requests[0].headers["x-tenant-id"] == TENANT_A


def test_missing_auth_returns_401_before_any_downstream_call(
    client: TestClient, fake_reporting_service: FakeReportingService
) -> None:
    response = client.get(f"/reports/{REPORT_OWNED_BY_A}")

    assert response.status_code == 401
    assert fake_reporting_service.seen_requests == []


def test_connection_failure_returns_502() -> None:
    fake = FakeReportingService(seen_requests=[], created_reports={}, simulate_connect_error=True)
    client = _build_client(fake)

    response = client.get(
        f"/reports/{REPORT_OWNED_BY_A}", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 502
    assert response.json()["detail"] == "downstream service unavailable"


def test_timeout_returns_504() -> None:
    fake = FakeReportingService(seen_requests=[], created_reports={}, simulate_timeout=True)
    client = _build_client(fake)

    response = client.post(
        "/reports/generate",
        json={"run_id": "run-a"},
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 504
    assert response.json()["detail"] == "downstream service timed out"
