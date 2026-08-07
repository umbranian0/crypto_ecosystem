"""GW-009: transport-level failure handling for `app.routers.runs`'s three
proxied calls to `validation-service`.

Reuses the same `httpx.MockTransport` pattern as GW-008's
`tests/test_runs_routing.py` -- the handler function raises
`httpx.ConnectError`/`httpx.TimeoutException` to simulate connection-refused
and timeout transport failures, and returns a normal `201`+
`{"status": "failed"}` response to prove that a validation-service *business*
failure (not a transport failure) is forwarded unmodified rather than
reinterpreted as a `502`/`504`/`500` (ticket Design section, explicit
non-goal).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.http_client import get_validation_service_client
from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord
from app.routers import runs

RAW_KEY_A = "tenant-a-raw-key"
TENANT_A = "tenant-a"

_DOWNSTREAM_HOSTNAME = "internal-validation-service.example"


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


def _client_for(handler) -> TestClient:
    app = FastAPI()
    app.include_router(runs.router)

    key_repo = FakeApiKeyRepository(
        {hashlib.sha256(RAW_KEY_A.encode()).hexdigest(): _api_key_record(RAW_KEY_A, TENANT_A)}
    )
    mock_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url=f"http://{_DOWNSTREAM_HOSTNAME}",
    )

    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    app.dependency_overrides[get_validation_service_client] = lambda: mock_client

    return TestClient(app)


_VALID_RUN_REQUEST = {
    "dataset_id": "dataset-a",
    "dataset_reference": {"kind": "inline", "values": [1, 2, 3]},
    "horizon": 5,
    "purge_gap_hours": 2,
    "train_window": 30,
    "test_window": 7,
    "step": 7,
}


def _connect_error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _timeout_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.TimeoutException("timed out", request=request)


def _failed_run_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(201, json={"id": "run-1", "status": "failed"})


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("post", "/runs", {"json": _VALID_RUN_REQUEST}),
        ("get", "/runs/some-run-id", {}),
        ("get", "/runs/some-run-id/splits", {}),
    ],
)
def test_connect_error_returns_502_with_generic_body(method, path, kwargs) -> None:
    client = _client_for(_connect_error_handler)

    response = getattr(client, method)(
        path, headers={"Authorization": f"Bearer {RAW_KEY_A}"}, **kwargs
    )

    assert response.status_code == 502
    body_text = response.text
    assert _DOWNSTREAM_HOSTNAME not in body_text
    assert "validation-service" not in body_text
    assert "Traceback" not in body_text


@pytest.mark.parametrize(
    ("method", "path", "kwargs"),
    [
        ("post", "/runs", {"json": _VALID_RUN_REQUEST}),
        ("get", "/runs/some-run-id", {}),
        ("get", "/runs/some-run-id/splits", {}),
    ],
)
def test_timeout_returns_504(method, path, kwargs) -> None:
    client = _client_for(_timeout_handler)

    response = getattr(client, method)(
        path, headers={"Authorization": f"Bearer {RAW_KEY_A}"}, **kwargs
    )

    assert response.status_code == 504
    assert _DOWNSTREAM_HOSTNAME not in response.text


def test_status_failed_response_passes_through_unmodified_not_reinterpreted() -> None:
    """Ticket's explicit non-goal (backlog AC3): a `201`+`status:"failed"`
    response from validation-service is a *successful* HTTP response, not a
    transport failure -- it must not be turned into a 502/504/500.
    """
    client = _client_for(_failed_run_handler)

    response = client.post(
        "/runs", json=_VALID_RUN_REQUEST, headers={"Authorization": f"Bearer {RAW_KEY_A}"}
    )

    assert response.status_code == 201
    assert response.json() == {"id": "run-1", "status": "failed"}
