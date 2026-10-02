"""RPT-002-03: `POST /reports/generate` accepts the optional `kind`/
`dataset_id`/`horizon` fields and forwards only what the caller sent."""

from __future__ import annotations

import hashlib
import json
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


def test_legacy_run_id_body_forwards_exact_payload() -> None:
    seen: list[httpx.Request] = []
    client = _client(seen, httpx.Response(201, json={"id": "r1", "status": "completed"}))

    response = client.post("/reports/generate", json={"run_id": "run-1"}, headers=HEADERS)

    assert response.status_code == 201
    assert json.loads(seen[0].content) == {"run_id": "run-1"}


def test_trend_body_forwards_kind_dataset_and_horizon() -> None:
    seen: list[httpx.Request] = []
    client = _client(seen, httpx.Response(201, json={"id": "r2", "status": "completed"}))
    body = {"kind": "consistency_trend", "dataset_id": "ds-1", "horizon": 24}

    response = client.post("/reports/generate", json=body, headers=HEADERS)

    assert response.status_code == 201
    assert response.json() == {"id": "r2", "status": "completed"}
    assert json.loads(seen[0].content) == body
    assert seen[0].headers["x-tenant-id"] == "tenant-a"


def test_downstream_422_passes_through() -> None:
    seen: list[httpx.Request] = []
    client = _client(seen, httpx.Response(422, json={"detail": "run_id is not allowed"}))

    response = client.post(
        "/reports/generate",
        json={"kind": "consistency_trend", "run_id": "x", "dataset_id": "d", "horizon": 1},
        headers=HEADERS,
    )

    assert response.status_code == 422
    assert len(seen) == 1


def test_unknown_kind_rejected_locally_without_downstream_call() -> None:
    seen: list[httpx.Request] = []
    client = _client(seen, httpx.Response(201, json={"id": "r", "status": "completed"}))

    response = client.post("/reports/generate", json={"kind": "bogus"}, headers=HEADERS)

    assert response.status_code == 422
    assert seen == []


def test_missing_key_returns_401_before_downstream() -> None:
    seen: list[httpx.Request] = []
    client = _client(seen, httpx.Response(201, json={"id": "r", "status": "completed"}))

    response = client.post("/reports/generate", json={"run_id": "run-1"})

    assert response.status_code == 401
    assert seen == []
