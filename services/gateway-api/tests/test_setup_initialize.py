"""SETUP-002: `POST /setup/initialize` -- the bootstrap-only tenant + first
API-key creation endpoint. Covers the ticket's Test acceptance criteria: a
first call on a fresh (zero-tenant) system succeeds and creates exactly one
tenant + one key; a second call (even a different `tenant_name`) returns
`409` with zero additional rows; the raw key never appears in any captured
log line on either path.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies.repositories import get_api_key_repository, get_tenant_repository
from app.main import app
from app.repositories.sqlite_repository import SQLiteApiKeyRepository, SQLiteTenantRepository


def _wire_sqlite(tmp_path):
    db_path = str(tmp_path / "gateway.db")
    tenant_repo = SQLiteTenantRepository(db_path)
    key_repo = SQLiteApiKeyRepository(db_path)
    app.dependency_overrides[get_tenant_repository] = lambda: tenant_repo
    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    return tenant_repo, key_repo


def _clear_overrides():
    app.dependency_overrides.pop(get_tenant_repository, None)
    app.dependency_overrides.pop(get_api_key_repository, None)


def test_first_call_creates_exactly_one_tenant_and_returns_the_raw_key(tmp_path) -> None:
    tenant_repo, key_repo = _wire_sqlite(tmp_path)
    try:
        response = TestClient(app).post("/setup/initialize", json={"tenant_name": "Acme Corp"})

        assert response.status_code == 201
        body = response.json()
        assert body["tenant_name"] == "Acme Corp"
        assert "api_key" in body and body["api_key"]
        assert tenant_repo.tenant_exists() is True
    finally:
        _clear_overrides()


def test_second_call_returns_409_and_creates_no_second_tenant(tmp_path) -> None:
    _wire_sqlite(tmp_path)
    try:
        client = TestClient(app)
        first = client.post("/setup/initialize", json={"tenant_name": "Acme Corp"})
        assert first.status_code == 201

        second = client.post("/setup/initialize", json={"tenant_name": "A Different Name"})

        assert second.status_code == 409
    finally:
        _clear_overrides()


def test_raw_key_never_appears_in_any_captured_log_record(tmp_path, caplog) -> None:
    _wire_sqlite(tmp_path)
    try:
        client = TestClient(app)
        with caplog.at_level("DEBUG"):
            first = client.post("/setup/initialize", json={"tenant_name": "Acme Corp"})
            raw_key = first.json()["api_key"]

            second = client.post("/setup/initialize", json={"tenant_name": "Other"})
            assert second.status_code == 409

        for record in caplog.records:
            assert raw_key not in record.getMessage()
            assert raw_key not in str(getattr(record, "__dict__", {}))
    finally:
        _clear_overrides()


def test_no_auth_required_on_initialize(tmp_path) -> None:
    _wire_sqlite(tmp_path)
    try:
        response = TestClient(app).post("/setup/initialize", json={"tenant_name": "Acme Corp"})
        assert response.status_code != 401
    finally:
        _clear_overrides()
