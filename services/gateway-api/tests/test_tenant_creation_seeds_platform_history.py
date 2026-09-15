"""GW-030: proves both tenant-creation front doors -- `POST /tenants`
(SETUP-011) and `POST /setup/initialize` (SETUP-002) -- route through the
same `provision()` call site and therefore both trigger exactly one seed
call to `ingestion-service`'s `POST /internal/seed-platform-history` for the
real newly created tenant's id.

Fakes the downstream with `httpx.MockTransport`, overriding
`get_ingestion_service_client` via `app.dependency_overrides` -- the same
pattern `test_operator_routing.py`/`test_downstream_failures.py` already
use -- even though `provision()` itself is a plain function, not a route
handler: overriding the FastAPI provider still works here because
`provision()` calls `get_ingestion_service_client` directly when no
`ingestion_client` is supplied, and `app.dependency_overrides` intercepts
calls to the provider function itself only when invoked through FastAPI's
resolution -- so these tests call the provider function directly via the
override mapping instead of relying on FastAPI's DI for a non-route
function.
"""

from __future__ import annotations

import json

import httpx
from fastapi.testclient import TestClient

from app.dependencies.http_client import get_ingestion_service_client
from app.dependencies.repositories import get_api_key_repository, get_tenant_repository
from app.main import app
from app.repositories.sqlite_repository import SQLiteApiKeyRepository, SQLiteTenantRepository

OPERATOR_TOKEN = "the-real-operator-token"
INTERNAL_TOKEN = "the-real-internal-token"


def _wire_sqlite(tmp_path):
    db_path = str(tmp_path / "gateway.db")
    tenant_repo = SQLiteTenantRepository(db_path)
    key_repo = SQLiteApiKeyRepository(db_path)
    app.dependency_overrides[get_tenant_repository] = lambda: tenant_repo
    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    return tenant_repo, key_repo


def _wire_mock_ingestion_client(handler, monkeypatch):
    """Overrides `app.provisioning`'s module-level call to
    `get_ingestion_service_client` by monkeypatching it directly --
    `provision()` calls the function by name at call time (not via
    `Depends()`), so `app.dependency_overrides` alone cannot intercept it
    from a plain function; patching the imported name in `app.provisioning`
    is the correct seam, mirroring how `app.provisioning` itself imports it.
    """
    mock_client = httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://internal-ingestion-service.example",
    )
    import app.provisioning as provisioning_module

    monkeypatch.setattr(provisioning_module, "get_ingestion_service_client", lambda: mock_client)


def _clear_overrides():
    app.dependency_overrides.pop(get_tenant_repository, None)
    app.dependency_overrides.pop(get_api_key_repository, None)


def test_post_tenants_triggers_exactly_one_seed_call_with_the_real_tenant_id(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setenv("INGESTION_INTERNAL_TOKEN", INTERNAL_TOKEN)
    _wire_sqlite(tmp_path)

    captured_requests = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"row_counts": {"price": 5}})

    _wire_mock_ingestion_client(_handler, monkeypatch)

    try:
        response = TestClient(app).post(
            "/tenants",
            json={"tenant_name": "Acme Corp"},
            headers={"X-Operator-Token": OPERATOR_TOKEN},
        )

        assert response.status_code == 201
        tenant_id = response.json()["tenant_id"]

        assert len(captured_requests) == 1
        assert captured_requests[0].url.path == "/internal/seed-platform-history"
        assert captured_requests[0].headers["x-internal-token"] == INTERNAL_TOKEN
        assert json.loads(captured_requests[0].content) == {"tenant_id": tenant_id}
    finally:
        _clear_overrides()


def test_post_setup_initialize_triggers_exactly_one_seed_call_with_the_real_tenant_id(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("INGESTION_INTERNAL_TOKEN", INTERNAL_TOKEN)
    _wire_sqlite(tmp_path)

    captured_requests = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"row_counts": {"price": 5}})

    _wire_mock_ingestion_client(_handler, monkeypatch)

    try:
        response = TestClient(app).post(
            "/setup/initialize", json={"tenant_name": "Acme Corp"}
        )

        assert response.status_code == 201
        tenant_id = response.json()["tenant_id"]

        assert len(captured_requests) == 1
        assert json.loads(captured_requests[0].content) == {"tenant_id": tenant_id}
    finally:
        _clear_overrides()


def test_post_tenants_downstream_connect_error_does_not_change_route_success_response(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setenv("INGESTION_INTERNAL_TOKEN", INTERNAL_TOKEN)
    _wire_sqlite(tmp_path)

    def _connect_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _wire_mock_ingestion_client(_connect_error_handler, monkeypatch)

    try:
        response = TestClient(app).post(
            "/tenants",
            json={"tenant_name": "Acme Corp"},
            headers={"X-Operator-Token": OPERATOR_TOKEN},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["tenant_name"] == "Acme Corp"
        assert "api_key" in body and body["api_key"]
    finally:
        _clear_overrides()


def test_post_tenants_downstream_500_does_not_change_route_success_response(
    tmp_path, monkeypatch
) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    monkeypatch.setenv("INGESTION_INTERNAL_TOKEN", INTERNAL_TOKEN)
    _wire_sqlite(tmp_path)

    def _server_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    _wire_mock_ingestion_client(_server_error_handler, monkeypatch)

    try:
        response = TestClient(app).post(
            "/tenants",
            json={"tenant_name": "Acme Corp"},
            headers={"X-Operator-Token": OPERATOR_TOKEN},
        )

        assert response.status_code == 201
        body = response.json()
        assert body["tenant_name"] == "Acme Corp"
        assert "api_key" in body and body["api_key"]
    finally:
        _clear_overrides()
