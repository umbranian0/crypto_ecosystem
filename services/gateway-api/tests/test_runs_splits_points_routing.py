"""RAV-016: `GET /runs/{run_id}/splits/points` pass-through proxy test.

Same `httpx.MockTransport` fake-backend pattern as
`test_runs_splits_summary_routing.py` (dedicated file, not appended there, so
this ticket's diff has no line overlap with that file). Asserts: repeated
`split_index` query params are forwarded correctly (not merged into one), and
the response is parsed into `SplitPoints` items.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.http_client import get_validation_service_client
from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord
from naive_first_common.logging import CorrelationIdMiddleware
from app.routers import runs

RAW_KEY_A = "tenant-a-raw-key"
TENANT_A = "tenant-a"

_POINT = {
    "timestamp": "2026-01-08T02:00:00",
    "predicted": 0.1,
    "actual": 0.2,
    "baseline_key": "naive0",
}

_SEED_POINTS: dict[int, list[dict]] = {
    0: [_POINT],
    1: [{**_POINT, "predicted": 0.3}],
    2: [],
}


@dataclass
class FakeValidationService:
    seen_requests: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen_requests.append(request)
        path = request.url.path

        if request.method == "GET" and path.endswith("/splits/points"):
            split_indices = [int(v) for v in request.url.params.get_list("split_index")]
            items = [
                {"split_index": idx, "points": _SEED_POINTS.get(idx, [])} for idx in split_indices
            ]
            return httpx.Response(200, json={"items": items})

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
def fake_validation_service() -> FakeValidationService:
    return FakeValidationService()


@pytest.fixture()
def client(fake_validation_service: FakeValidationService) -> TestClient:
    app = FastAPI()
    app.include_router(runs.router)
    app.add_middleware(CorrelationIdMiddleware)

    key_repo = FakeApiKeyRepository(
        {hashlib.sha256(RAW_KEY_A.encode()).hexdigest(): _api_key_record(RAW_KEY_A, TENANT_A)}
    )
    mock_client = httpx.Client(
        transport=httpx.MockTransport(fake_validation_service.handler),
        base_url="http://validation-service",
    )

    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    app.dependency_overrides[get_validation_service_client] = lambda: mock_client

    return TestClient(app)


def test_splits_points_forwards_repeated_split_index_params_and_parses_items(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.get(
        "/runs/run-1/splits/points",
        params=[("split_index", 0), ("split_index", 1), ("split_index", 2)],
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"items"}
    items_by_split = {item["split_index"]: item["points"] for item in body["items"]}
    assert set(items_by_split.keys()) == {0, 1, 2}
    assert items_by_split[0] == _SEED_POINTS[0]
    assert items_by_split[1] == _SEED_POINTS[1]
    assert items_by_split[2] == []

    seen = fake_validation_service.seen_requests[-1]
    assert seen.url.params.get_list("split_index") == ["0", "1", "2"]


def test_splits_points_empty_split_index_list_forwards_no_split_index_params(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.get(
        "/runs/run-1/splits/points", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"items": []}

    seen = fake_validation_service.seen_requests[-1]
    assert seen.url.params.get_list("split_index") == []


def test_splits_points_missing_auth_returns_401_before_any_downstream_call(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.get("/runs/run-1/splits/points", params=[("split_index", 0)])

    assert response.status_code == 401
    assert fake_validation_service.seen_requests == []
