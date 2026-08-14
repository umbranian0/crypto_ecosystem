"""RS-005: `GET /reports/{id}`.

Uses an in-memory fake `ReportRepository` injected via
`app.dependency_overrides` (GW-006/GW-007 precedent for repository fakes in
this repo, per the ticket's own environment notes) rather than real
Postgres -- `ReportRepository` is a `typing.Protocol` with no `sqlalchemy`
import, so a plain dataclass-backed fake satisfies it fully.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.repositories import get_report_repository
from app.repositories.interfaces import ReportRecord
from app.routers import report_retrieval

TENANT_A = "tenant-a"
TENANT_B = "tenant-b"

REPORT_OWNED_BY_A = "report-owned-by-a"
REPORT_OWNED_BY_B = "report-owned-by-b"

_GENERATED_AT = datetime(2026, 1, 1, tzinfo=timezone.utc)

_SEED_REPORTS: dict[str, ReportRecord] = {
    REPORT_OWNED_BY_A: ReportRecord(
        id=REPORT_OWNED_BY_A,
        tenant_id=TENANT_A,
        run_id="run-a",
        report_kind="validation_audit",
        generated_at=_GENERATED_AT,
        content="<html>report a</html>",
        status="generated",
    ),
    REPORT_OWNED_BY_B: ReportRecord(
        id=REPORT_OWNED_BY_B,
        tenant_id=TENANT_B,
        run_id="run-b",
        report_kind="validation_audit",
        generated_at=_GENERATED_AT,
        content="<html>report b</html>",
        status="generated",
    ),
}


@dataclass
class FakeReportRepository:
    """Mirrors `ReportRepository.get_report`'s real non-disclosure contract
    (RS-002): returns `None` for both "doesn't exist" and "wrong tenant".
    """

    reports: dict[str, ReportRecord] = field(default_factory=lambda: dict(_SEED_REPORTS))

    def create_report(
        self, tenant_id: str, run_id: str, report_kind: str, content: str, status: str
    ) -> ReportRecord:  # pragma: no cover
        raise NotImplementedError

    def get_report(self, tenant_id: str, report_id: str) -> ReportRecord | None:
        report = self.reports.get(report_id)
        if report is None or report.tenant_id != tenant_id:
            return None
        return report


@pytest.fixture()
def fake_repository() -> FakeReportRepository:
    return FakeReportRepository()


@pytest.fixture()
def client(fake_repository: FakeReportRepository) -> TestClient:
    app = FastAPI()
    app.include_router(report_retrieval.router, prefix="/reports")
    app.dependency_overrides[get_report_repository] = lambda: fake_repository
    return TestClient(app)


def test_get_report_success_returns_full_shape(client: TestClient) -> None:
    response = client.get(
        f"/reports/{REPORT_OWNED_BY_A}", headers={"X-Tenant-Id": TENANT_A}
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
    assert body["report_kind"] == "validation_audit"
    assert body["status"] == "generated"
    assert body["content"] == "<html>report a</html>"


def test_get_report_nonexistent_id_returns_404(client: TestClient) -> None:
    response = client.get("/reports/does-not-exist", headers={"X-Tenant-Id": TENANT_A})

    assert response.status_code == 404


def test_cross_tenant_report_returns_identical_404_to_nonexistent(
    client: TestClient,
) -> None:
    """Non-tautological proof (ticket Test AC3): the cross-tenant response
    body must be field-for-field identical to the nonexistent-id response
    body, not merely also a 404.
    """
    cross_tenant_response = client.get(
        f"/reports/{REPORT_OWNED_BY_B}", headers={"X-Tenant-Id": TENANT_A}
    )
    nonexistent_response = client.get(
        "/reports/does-not-exist", headers={"X-Tenant-Id": TENANT_A}
    )

    assert cross_tenant_response.status_code == 404
    assert nonexistent_response.status_code == 404
    assert cross_tenant_response.json() == nonexistent_response.json()


def test_same_report_visible_to_owning_tenant(client: TestClient) -> None:
    response = client.get(
        f"/reports/{REPORT_OWNED_BY_B}", headers={"X-Tenant-Id": TENANT_B}
    )

    assert response.status_code == 200
    assert response.json()["id"] == REPORT_OWNED_BY_B


def test_missing_tenant_header_returns_401(client: TestClient) -> None:
    response = client.get(f"/reports/{REPORT_OWNED_BY_A}")

    assert response.status_code == 401
