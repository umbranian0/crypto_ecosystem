"""SETUP-011: `app.routers.tenants` (`GET /tenants`, `POST /tenants`,
`POST /tenants/{tenant_id}/api-keys/{key_id}/revoke`).

Wires the real `SQLiteTenantRepository`/`SQLiteApiKeyRepository` (file-based,
`tmp_path`) through the real `app.main.app`, the same override pattern
`test_setup_initialize.py` already established, so these tests exercise the
real repository + router wiring, not a hand-rolled fake.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.dependencies.repositories import get_api_key_repository, get_tenant_repository
from app.main import app
from app.repositories.sqlite_repository import SQLiteApiKeyRepository, SQLiteTenantRepository

OPERATOR_TOKEN = "the-real-operator-token"


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


def _op_headers():
    return {"X-Operator-Token": OPERATOR_TOKEN}


def test_list_tenants_empty(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    _wire_sqlite(tmp_path)
    try:
        response = TestClient(app).get("/tenants", headers=_op_headers())

        assert response.status_code == 200
        assert response.json() == {"items": []}
    finally:
        _clear_overrides()


def test_list_tenants_one_tenant_with_active_key(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")
        key = key_repo.create_key(tenant.id, "hash-abc")

        response = TestClient(app).get("/tenants", headers=_op_headers())

        assert response.status_code == 200
        body = response.json()
        assert len(body["items"]) == 1
        item = body["items"][0]
        assert item["id"] == tenant.id
        assert item["name"] == "Acme Corp"
        assert len(item["api_keys"]) == 1
        assert item["api_keys"][0]["id"] == key.id
        assert item["api_keys"][0]["revoked_at"] is None
        # never expose key_hash or a raw key anywhere in the response.
        assert "key_hash" not in item["api_keys"][0]
        assert "hash-abc" not in response.text
    finally:
        _clear_overrides()


def test_list_tenants_multiple_tenants_mixed_active_and_revoked_keys(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo = _wire_sqlite(tmp_path)
    try:
        tenant_a = tenant_repo.create_tenant("Tenant A")
        tenant_b = tenant_repo.create_tenant("Tenant B")
        active_key = key_repo.create_key(tenant_a.id, "hash-active")
        revoked_key = key_repo.create_key(tenant_a.id, "hash-revoked")
        key_repo.revoke_key(tenant_a.id, revoked_key.id)
        key_repo.create_key(tenant_b.id, "hash-b")

        response = TestClient(app).get("/tenants", headers=_op_headers())

        assert response.status_code == 200
        body = response.json()
        assert {item["id"] for item in body["items"]} == {tenant_a.id, tenant_b.id}
        tenant_a_body = next(item for item in body["items"] if item["id"] == tenant_a.id)
        keys_by_id = {key["id"]: key for key in tenant_a_body["api_keys"]}
        assert keys_by_id[active_key.id]["revoked_at"] is None
        assert keys_by_id[revoked_key.id]["revoked_at"] is not None
    finally:
        _clear_overrides()


def test_list_tenants_requires_operator_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    _wire_sqlite(tmp_path)
    try:
        response = TestClient(app).get("/tenants")

        assert response.status_code == 401
    finally:
        _clear_overrides()


def test_create_tenant_returns_raw_key_once_and_persists(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, _ = _wire_sqlite(tmp_path)
    try:
        response = TestClient(app).post(
            "/tenants", json={"tenant_name": "Acme Corp"}, headers=_op_headers()
        )

        assert response.status_code == 201
        body = response.json()
        assert body["tenant_name"] == "Acme Corp"
        assert "api_key" in body and body["api_key"]
        assert tenant_repo.get_tenant(body["tenant_id"]) is not None
    finally:
        _clear_overrides()


def test_create_tenant_requires_operator_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    _wire_sqlite(tmp_path)
    try:
        response = TestClient(app).post("/tenants", json={"tenant_name": "Acme Corp"})

        assert response.status_code == 401
    finally:
        _clear_overrides()


def test_create_tenant_has_no_already_initialized_guard(tmp_path, monkeypatch) -> None:
    """Unlike POST /setup/initialize, this route creates a second, third,
    etc. tenant without a 409 -- a genuine ongoing multi-tenant creation
    surface, gated by operator auth instead of the fresh-install check.
    """
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    _wire_sqlite(tmp_path)
    try:
        client = TestClient(app)
        first = client.post("/tenants", json={"tenant_name": "Tenant One"}, headers=_op_headers())
        second = client.post("/tenants", json={"tenant_name": "Tenant Two"}, headers=_op_headers())

        assert first.status_code == 201
        assert second.status_code == 201
        assert first.json()["tenant_id"] != second.json()["tenant_id"]
    finally:
        _clear_overrides()


def test_revoke_fresh_key_sets_revoked_at(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")
        key = key_repo.create_key(tenant.id, "hash-to-revoke")

        response = TestClient(app).post(
            f"/tenants/{tenant.id}/api-keys/{key.id}/revoke", headers=_op_headers()
        )

        assert response.status_code == 200
        body = response.json()
        assert body["tenant_id"] == tenant.id
        assert body["key_id"] == key.id
        assert body["revoked_at"] is not None
        assert key_repo.get_by_hash("hash-to-revoke").revoked_at is not None
    finally:
        _clear_overrides()


def test_revoke_already_revoked_key_is_a_no_op_with_unchanged_timestamp(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")
        key = key_repo.create_key(tenant.id, "hash-to-revoke")
        client = TestClient(app)

        first = client.post(f"/tenants/{tenant.id}/api-keys/{key.id}/revoke", headers=_op_headers())
        assert first.status_code == 200
        first_revoked_at = first.json()["revoked_at"]

        second = client.post(f"/tenants/{tenant.id}/api-keys/{key.id}/revoke", headers=_op_headers())

        assert second.status_code == 200
        assert second.json()["revoked_at"] == first_revoked_at
    finally:
        _clear_overrides()


def test_revoke_unknown_key_id_returns_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, _ = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")

        response = TestClient(app).post(
            f"/tenants/{tenant.id}/api-keys/no-such-key/revoke", headers=_op_headers()
        )

        assert response.status_code == 404
    finally:
        _clear_overrides()


def test_revoke_key_belonging_to_a_different_tenant_returns_404(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo = _wire_sqlite(tmp_path)
    try:
        tenant_a = tenant_repo.create_tenant("Tenant A")
        tenant_b = tenant_repo.create_tenant("Tenant B")
        key_a = key_repo.create_key(tenant_a.id, "hash-a")

        response = TestClient(app).post(
            f"/tenants/{tenant_b.id}/api-keys/{key_a.id}/revoke", headers=_op_headers()
        )

        assert response.status_code == 404
        # the key must not actually be revoked by the cross-tenant attempt.
        assert key_repo.get_by_hash("hash-a").revoked_at is None
    finally:
        _clear_overrides()


def test_revoke_requires_operator_auth(tmp_path, monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")
        key = key_repo.create_key(tenant.id, "hash-x")

        response = TestClient(app).post(f"/tenants/{tenant.id}/api-keys/{key.id}/revoke")

        assert response.status_code == 401
    finally:
        _clear_overrides()


def test_a_tenants_own_api_key_is_rejected_on_every_tenants_route(tmp_path, monkeypatch) -> None:
    """Cross-boundary guard this whole epic exists for: a real, valid
    tenant API key presented as the operator credential must never satisfy
    get_authenticated_operator (SETUP-010's 403 branch -- a real credential,
    wrong kind for this gate).
    """
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    tenant_repo, key_repo = _wire_sqlite(tmp_path)
    try:
        tenant = tenant_repo.create_tenant("Acme Corp")
        raw_key = "tenant-a-real-raw-key"
        import hashlib

        key_repo.create_key(tenant.id, hashlib.sha256(raw_key.encode()).hexdigest())
        client = TestClient(app)
        tenant_headers = {"X-Operator-Token": raw_key}

        list_response = client.get("/tenants", headers=tenant_headers)
        create_response = client.post(
            "/tenants", json={"tenant_name": "Other"}, headers=tenant_headers
        )

        assert list_response.status_code == 403
        assert create_response.status_code == 403
    finally:
        _clear_overrides()
