"""ADMIN-002-01: `identity.operator_audit_log` write-on-success wiring
(`POST /tenants`, `POST /tenants/{tenant_id}/api-keys/{key_id}/revoke`) and
the read side, `GET /operator-audit-log`.

Wires the real `SQLiteTenantRepository`/`SQLiteApiKeyRepository`/
`SQLiteOperatorAuditLogRepository` (file-based, `tmp_path`) through the real
`app.main.app`, the same `app.dependency_overrides` pattern
`tests/test_tenants_router.py` already establishes -- not a hand-rolled fake.
"""

from __future__ import annotations

import hashlib

from fastapi.testclient import TestClient

from app.dependencies.repositories import (
    get_api_key_repository,
    get_operator_audit_log_repository,
    get_tenant_repository,
)
from app.main import app
from app.repositories.sqlite_repository import (
    SQLiteApiKeyRepository,
    SQLiteOperatorAuditLogRepository,
    SQLiteTenantRepository,
)

OPERATOR_TOKEN = "the-real-operator-token"


def _wire_sqlite(tmp_path):
    db_path = str(tmp_path / "gateway.db")
    tenant_repo = SQLiteTenantRepository(db_path)
    key_repo = SQLiteApiKeyRepository(db_path)
    audit_log_repo = SQLiteOperatorAuditLogRepository(db_path)
    app.dependency_overrides[get_tenant_repository] = lambda: tenant_repo
    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    app.dependency_overrides[get_operator_audit_log_repository] = lambda: audit_log_repo
    return tenant_repo, key_repo, audit_log_repo


def _clear_overrides():
    app.dependency_overrides.pop(get_tenant_repository, None)
    app.dependency_overrides.pop(get_api_key_repository, None)
    app.dependency_overrides.pop(get_operator_audit_log_repository, None)


def _op_headers():
    return {"X-Operator-Token": OPERATOR_TOKEN}


def test_create_tenant_writes_one_audit_log_row_on_success(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    _, _, audit_log_repo = _wire_sqlite(tmp_path)
    try:
        response = TestClient(app).post(
            "/tenants", json={"tenant_name": "Acme Corp"}, headers=_op_headers()
        )

        assert response.status_code == 201
        tenant_id = response.json()["tenant_id"]
        correlation_id = response.headers["X-Correlation-Id"]

        entries, total = audit_log_repo.list_entries(limit=10, offset=0)
        assert total == 1
        assert len(entries) == 1
        assert entries[0].action == "tenant.create"
        assert entries[0].target_tenant_id == tenant_id
        assert entries[0].correlation_id == correlation_id
    finally:
        _clear_overrides()


def test_revoke_api_key_writes_one_audit_log_row_on_success(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo, audit_log_repo = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")
        key = key_repo.create_key(tenant.id, "hash-to-revoke")

        response = TestClient(app).post(
            f"/tenants/{tenant.id}/api-keys/{key.id}/revoke", headers=_op_headers()
        )

        assert response.status_code == 200
        correlation_id = response.headers["X-Correlation-Id"]

        entries, total = audit_log_repo.list_entries(limit=10, offset=0)
        assert total == 1
        assert entries[0].action == "api_key.revoke"
        assert entries[0].target_tenant_id == tenant.id
        assert entries[0].correlation_id == correlation_id
    finally:
        _clear_overrides()


def test_revoke_already_revoked_key_still_writes_one_audit_log_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo, audit_log_repo = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")
        key = key_repo.create_key(tenant.id, "hash-to-revoke")
        client = TestClient(app)

        first = client.post(f"/tenants/{tenant.id}/api-keys/{key.id}/revoke", headers=_op_headers())
        second = client.post(f"/tenants/{tenant.id}/api-keys/{key.id}/revoke", headers=_op_headers())

        assert first.status_code == 200
        assert second.status_code == 200

        _, total = audit_log_repo.list_entries(limit=10, offset=0)
        assert total == 2
    finally:
        _clear_overrides()


def test_revoke_unknown_key_writes_no_audit_log_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, _, audit_log_repo = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")

        response = TestClient(app).post(
            f"/tenants/{tenant.id}/api-keys/no-such-key/revoke", headers=_op_headers()
        )

        assert response.status_code == 404
        _, total = audit_log_repo.list_entries(limit=10, offset=0)
        assert total == 0
    finally:
        _clear_overrides()


def test_create_tenant_without_operator_token_writes_no_audit_log_row(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    _, _, audit_log_repo = _wire_sqlite(tmp_path)
    try:
        response = TestClient(app).post("/tenants", json={"tenant_name": "Acme Corp"})

        assert response.status_code == 401
        _, total = audit_log_repo.list_entries(limit=10, offset=0)
        assert total == 0
    finally:
        _clear_overrides()


def test_operator_audit_log_row_never_contains_operator_token(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo, audit_log_repo = _wire_sqlite(tmp_path)
    try:
        client = TestClient(app)
        tenant = tenant_repo.create_tenant("Acme Corp")
        key = key_repo.create_key(tenant.id, "hash-to-revoke")

        client.post("/tenants", json={"tenant_name": "Other Co"}, headers=_op_headers())
        client.post(f"/tenants/{tenant.id}/api-keys/{key.id}/revoke", headers=_op_headers())
        client.post("/tenants", json={"tenant_name": "No Auth"})

        token_hash = hashlib.sha256(OPERATOR_TOKEN.encode()).hexdigest()
        entries, _ = audit_log_repo.list_entries(limit=100, offset=0)
        assert entries
        for entry in entries:
            for value in (entry.id, entry.action, entry.target_tenant_id, entry.correlation_id):
                assert OPERATOR_TOKEN != value
                assert token_hash != value
                if value is not None:
                    assert OPERATOR_TOKEN not in value
                    assert token_hash not in value

        list_response = client.get("/operator-audit-log", headers=_op_headers())
        assert OPERATOR_TOKEN not in list_response.text
        assert token_hash not in list_response.text
    finally:
        _clear_overrides()


def test_get_operator_audit_log_requires_operator_session(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    _wire_sqlite(tmp_path)
    try:
        response = TestClient(app).get("/operator-audit-log")

        assert response.status_code == 401
    finally:
        _clear_overrides()


def test_get_operator_audit_log_paginates(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, _, audit_log_repo = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")
        for i in range(3):
            audit_log_repo.record("tenant.create", tenant.id, f"correlation-{i}")

        client = TestClient(app)

        first_page = client.get("/operator-audit-log?limit=2&offset=0", headers=_op_headers())
        second_page = client.get("/operator-audit-log?limit=2&offset=2", headers=_op_headers())

        assert first_page.status_code == 200
        first_body = first_page.json()
        assert len(first_body["items"]) == 2
        assert first_body["total"] == 3
        assert first_body["limit"] == 2
        assert first_body["offset"] == 0

        second_body = second_page.json()
        assert len(second_body["items"]) == 1
        assert second_body["total"] == 3
    finally:
        _clear_overrides()
