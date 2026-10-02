"""RPT-004-02: `GET /reports/{id}/diff/{other_id}` is a verbatim pass-through."""

from __future__ import annotations

import hashlib
from datetime import datetime, timezone

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.http_client import get_reporting_service_client
from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord
from app.routers import reports

RAW_KEY = "tenant-a-raw-key"
HEADERS = {"X-Api-Key": RAW_KEY}


class _KeyRepo:
    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        if key_hash != hashlib.sha256(RAW_KEY.encode()).hexdigest():
            return None
        return ApiKeyRecord(
            id="key-a",
            tenant_id="tenant-a",
            key_hash=key_hash,
            created_at=datetime.now(timezone.utc),
            revoked_at=None,
        )


def _client(seen: list[httpx.Request], response: httpx.Response) -> TestClient:
    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return response

    app = FastAPI()
    app.include_router(reports.router)
    mock = httpx.Client(transport=httpx.MockTransport(handler), base_url="http://reporting-service")
    app.dependency_overrides[get_api_key_repository] = lambda: _KeyRepo()
    app.dependency_overrides[get_reporting_service_client] = lambda: mock
    return TestClient(app)


def test_diff_forwards_path_and_tenant_and_returns_body_verbatim() -> None:
    seen: list[httpx.Request] = []
    body = {"report_id": "r1", "other_report_id": "r2", "splits": [], "extra_field": {"a": 1}}
    client = _client(seen, httpx.Response(200, json=body))

    response = client.get("/reports/r1/diff/r2", headers=HEADERS)

    assert response.status_code == 200
    assert response.json() == body
    assert len(seen) == 1
    assert seen[0].url.path == "/reports/r1/diff/r2"
    assert seen[0].headers["x-tenant-id"] == "tenant-a"


def test_diff_downstream_404_passes_through() -> None:
    seen: list[httpx.Request] = []
    client = _client(seen, httpx.Response(404, json={"detail": "report not found"}))

    response = client.get("/reports/r1/diff/nope", headers=HEADERS)

    assert response.status_code == 404


def test_diff_downstream_422_passes_through() -> None:
    seen: list[httpx.Request] = []
    client = _client(seen, httpx.Response(422, json={"detail": "runs are not comparable"}))

    response = client.get("/reports/r1/diff/r2", headers=HEADERS)

    assert response.status_code == 422


def test_diff_missing_key_returns_401_before_downstream() -> None:
    seen: list[httpx.Request] = []
    client = _client(seen, httpx.Response(200, json={}))

    response = client.get("/reports/r1/diff/r2")

    assert response.status_code == 401
    assert seen == []


def test_single_report_route_not_shadowed_by_diff_route() -> None:
    seen: list[httpx.Request] = []
    client = _client(seen, httpx.Response(404, json={"detail": "report not found"}))

    client.get("/reports/r1", headers=HEADERS)

    assert seen[0].url.path == "/reports/r1"
