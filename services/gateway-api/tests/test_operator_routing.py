"""GW-021/INGEST-012: `app.routers.operator` (`GET /ingestion/connectors/credentials-status`).

Fakes `ingestion-service` with `httpx.MockTransport` (same pattern
`test_downstream_failures.py`/`test_runs_routing.py` already use), proving:
the route is gated by `get_authenticated_operator` (not tenant auth), a
required `tenant_id` query parameter is forwarded downstream as
`X-Tenant-Id`, a missing `tenant_id` is a `422` before any downstream call,
a successful downstream response is forwarded unmodified, and a downstream
transport failure is translated via the reused `_call_downstream`/
`_raise_for_error` helpers (GW-009), exactly like `runs.py`/`reports.py`.

`INGEST-012`: `ingestion-service` now implements this endpoint for real
(previously it did not exist, INGEST-004/009 territory) -- these tests
still fake the transport layer entirely, so they exercise this router's
own contract in isolation, independent of ingestion-service's own test
suite (`services/ingestion-service/tests/test_credentials_status_router.py`).
"""

from __future__ import annotations

import httpx
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.http_client import get_ingestion_service_client
from app.dependencies.operator_auth import get_authenticated_operator
from app.routers import operator

OPERATOR_TOKEN = "the-real-operator-token"


def _client_for(handler) -> TestClient:
    app = FastAPI()
    app.include_router(operator.router)

    mock_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://internal-ingestion-service.example",
    )
    app.dependency_overrides[get_ingestion_service_client] = lambda: mock_client

    return TestClient(app)


def _success_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "items": [
                {"source": "reddit_vader_sentiment", "credential_set": True, "last_set_at": "2026-08-01T00:00:00Z"}
            ]
        },
    )


def _connect_error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def test_missing_operator_token_returns_401_before_any_downstream_call(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)

    def _fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError("downstream must not be called when operator auth fails")

    client = _client_for(_fail_if_called)

    response = client.get("/ingestion/connectors/credentials-status", params={"tenant_id": "tenant-a"})

    assert response.status_code == 401


def test_missing_tenant_id_returns_422_before_any_downstream_call(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)

    def _fail_if_called(request: httpx.Request) -> httpx.Response:
        raise AssertionError("downstream must not be called when tenant_id is missing")

    client = _client_for(_fail_if_called)

    response = client.get(
        "/ingestion/connectors/credentials-status",
        headers={"X-Operator-Token": OPERATOR_TOKEN},
    )

    assert response.status_code == 422


def test_valid_operator_token_and_tenant_id_forwards_and_returns_downstream_body(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    captured_requests = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return _success_handler(request)

    client = _client_for(_handler)

    response = client.get(
        "/ingestion/connectors/credentials-status",
        params={"tenant_id": "tenant-a"},
        headers={"X-Operator-Token": OPERATOR_TOKEN},
    )

    assert response.status_code == 200
    assert response.json() == {
        "items": [
            {"source": "reddit_vader_sentiment", "credential_set": True, "last_set_at": "2026-08-01T00:00:00Z"}
        ]
    }
    assert len(captured_requests) == 1
    assert captured_requests[0].headers["x-tenant-id"] == "tenant-a"


def test_downstream_connect_error_returns_502_reusing_gw009_handling(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    client = _client_for(_connect_error_handler)

    response = client.get(
        "/ingestion/connectors/credentials-status",
        params={"tenant_id": "tenant-a"},
        headers={"X-Operator-Token": OPERATOR_TOKEN},
    )

    assert response.status_code == 502
    assert "internal-ingestion-service" not in response.text
