"""RAV-012: `GET /runs/splits/summary` pass-through proxy test.

Same `httpx.MockTransport` fake-backend pattern as `test_runs_routing.py`
(dedicated file, not appended there, so this ticket's diff has no line
overlap with that file). Asserts: `run_id` list query params are forwarded
correctly (repeated params, not merged into one), and the response is
parsed into `RunSplitSummary` items.
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_authenticated_tenant  # noqa: F401 (import parity with test_runs_routing.py)
from app.dependencies.http_client import get_validation_service_client
from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord
from naive_first_common.logging import CorrelationIdMiddleware
from app.routers import runs

RAW_KEY_A = "tenant-a-raw-key"
TENANT_A = "tenant-a"

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
    "client_baseline": None,
    "has_client_model": False,
}

_SEED_SUMMARY: dict[str, list[dict]] = {
    "run-a": [_SPLIT_RECORD],
    "run-b": [{**_SPLIT_RECORD, "split_index": 1}],
}


@dataclass
class FakeValidationService:
    seen_requests: list[httpx.Request] = field(default_factory=list)

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.seen_requests.append(request)
        path = request.url.path

        if request.method == "GET" and path == "/runs/splits/summary":
            run_ids = request.url.params.get_list("run_id")
            items = [
                {"run_id": run_id, "splits": _SEED_SUMMARY[run_id]}
                for run_id in run_ids
                if run_id in _SEED_SUMMARY
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


def test_splits_summary_forwards_repeated_run_id_params_and_parses_items(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.get(
        "/runs/splits/summary",
        params=[("run_id", "run-a"), ("run_id", "run-b")],
        headers={"Authorization": f"Bearer {RAW_KEY_A}"},
    )

    assert response.status_code == 200, response.text
    body = response.json()
    assert set(body.keys()) == {"items"}
    items_by_run_id = {item["run_id"]: item["splits"] for item in body["items"]}
    assert set(items_by_run_id.keys()) == {"run-a", "run-b"}
    assert items_by_run_id["run-a"] == _SEED_SUMMARY["run-a"]
    assert items_by_run_id["run-b"] == _SEED_SUMMARY["run-b"]

    seen = fake_validation_service.seen_requests[-1]
    assert seen.url.params.get_list("run_id") == ["run-a", "run-b"]


def test_splits_summary_empty_run_id_list_forwards_no_run_id_params(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.get(
        "/runs/splits/summary", headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 200, response.text
    assert response.json() == {"items": []}

    seen = fake_validation_service.seen_requests[-1]
    assert seen.url.params.get_list("run_id") == []


def test_splits_summary_missing_auth_returns_401_before_any_downstream_call(
    client: TestClient, fake_validation_service: FakeValidationService
) -> None:
    response = client.get("/runs/splits/summary", params=[("run_id", "run-a")])

    assert response.status_code == 401
    assert fake_validation_service.seen_requests == []
