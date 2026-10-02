"""ADMIN-005-02: `app.routers.me_api_keys` against the real SQLite repositories
wired through the real `app.main.app`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from app.dependencies.repositories import (
    get_api_key_repository,
    get_operator_audit_log_repository,
    get_tenant_repository,
)
from app.main import app
from app.provisioning import mint_api_key
from app.repositories.sqlite_repository import (
    SQLiteApiKeyRepository,
    SQLiteOperatorAuditLogRepository,
    SQLiteTenantRepository,
)


class Env:
    def __init__(self, tmp_path):
        db_path = str(tmp_path / "gateway.db")
        self.tenants = SQLiteTenantRepository(db_path)
        self.keys = SQLiteApiKeyRepository(db_path)
        self.audit = SQLiteOperatorAuditLogRepository(db_path)
        self.client = TestClient(app)

    def tenant_with_keys(self, name: str, count: int):
        tenant = self.tenants.create_tenant(name)
        minted = [mint_api_key(tenant.id, self.keys) for _ in range(count)]
        return tenant, minted

    def actions(self) -> list[str]:
        return [e.action for e in self.audit.list_entries(100, 0)[0]]


@pytest.fixture
def env(tmp_path, monkeypatch):
    monkeypatch.setenv("OPERATOR_TOKEN", "the-real-operator-token")
    e = Env(tmp_path)
    app.dependency_overrides[get_tenant_repository] = lambda: e.tenants
    app.dependency_overrides[get_api_key_repository] = lambda: e.keys
    app.dependency_overrides[get_operator_audit_log_repository] = lambda: e.audit
    yield e
    for dep in (get_tenant_repository, get_api_key_repository, get_operator_audit_log_repository):
        app.dependency_overrides.pop(dep, None)


def _auth(raw_key: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {raw_key}"}


def test_mint_returns_raw_key_once_no_store_and_it_authenticates(env) -> None:
    _, [(record, raw)] = env.tenant_with_keys("A", 1)

    response = env.client.post("/me/api-keys", headers=_auth(raw))

    assert response.status_code == 201
    assert response.headers["cache-control"] == "no-store"
    body = response.json()
    new_raw = body["api_key"]
    assert env.client.get("/me/api-keys", headers=_auth(new_raw)).status_code == 200
    listing = env.client.get("/me/api-keys", headers=_auth(raw))
    assert new_raw not in listing.text
    assert {k["id"] for k in listing.json()["items"]} == {record.id, body["id"]}
    assert env.actions() == ["api_key.self_create"]


def test_list_marks_current_includes_revoked_and_hides_secrets(env) -> None:
    tenant, [(k1, raw1), (k2, _raw2)] = env.tenant_with_keys("A", 2)
    env.keys.revoke_key(tenant.id, k2.id)

    response = env.client.get("/me/api-keys", headers=_auth(raw1))

    assert response.status_code == 200
    items = {i["id"]: i for i in response.json()["items"]}
    assert items[k1.id]["current"] is True
    assert items[k2.id]["current"] is False
    assert items[k2.id]["revoked_at"] is not None
    assert "key_hash" not in response.text
    assert raw1 not in response.text


def test_revoke_other_key_then_it_gets_401(env) -> None:
    _, [(_k1, raw1), (k2, raw2)] = env.tenant_with_keys("A", 2)

    response = env.client.post(f"/me/api-keys/{k2.id}/revoke", headers=_auth(raw1))

    assert response.status_code == 200
    assert response.json()["key_id"] == k2.id
    assert response.json()["revoked_at"] is not None
    assert env.client.get("/me/api-keys", headers=_auth(raw2)).status_code == 401
    assert env.actions() == ["api_key.self_revoke"]


def test_revoke_own_key_409(env) -> None:
    _, [(k1, raw1), _] = env.tenant_with_keys("A", 2)

    response = env.client.post(f"/me/api-keys/{k1.id}/revoke", headers=_auth(raw1))

    assert response.status_code == 409
    assert "authenticating" in response.json()["detail"]
    assert env.client.get("/me/api-keys", headers=_auth(raw1)).status_code == 200
    assert env.actions() == []


def test_revoke_last_active_key_409(env) -> None:
    # Unreachable over plain HTTP without a race (caller and target are both
    # active, so >=2 active keys), so the repository's guard outcome is stubbed;
    # the guard itself is covered in the repository tests.
    _, [(_k1, raw1), (k2, _raw2)] = env.tenant_with_keys("A", 2)

    class LastActive:
        def __init__(self, inner):
            self._inner = inner

        def __getattr__(self, name):
            return getattr(self._inner, name)

        def revoke_key_if_not_last_active(self, tenant_id, key_id):
            return "last_active"

    app.dependency_overrides[get_api_key_repository] = lambda: LastActive(env.keys)

    response = env.client.post(f"/me/api-keys/{k2.id}/revoke", headers=_auth(raw1))

    assert response.status_code == 409
    assert "last active" in response.json()["detail"]
    assert env.actions() == []


def test_revoke_already_revoked_is_200_noop_with_audit(env) -> None:
    tenant, [(_k1, raw1), (k2, _raw2)] = env.tenant_with_keys("A", 2)
    first = env.client.post(f"/me/api-keys/{k2.id}/revoke", headers=_auth(raw1))

    second = env.client.post(f"/me/api-keys/{k2.id}/revoke", headers=_auth(raw1))

    assert second.status_code == 200
    assert second.json()["revoked_at"] == first.json()["revoked_at"]
    assert env.actions() == ["api_key.self_revoke", "api_key.self_revoke"]


def test_cross_tenant_isolation(env) -> None:
    _, [(_a1, raw_a)] = env.tenant_with_keys("A", 1)
    tenant_b, [(kb, raw_b)] = env.tenant_with_keys("B", 1)

    listing = env.client.get("/me/api-keys", headers=_auth(raw_a))
    response = env.client.post(f"/me/api-keys/{kb.id}/revoke", headers=_auth(raw_a))
    missing = env.client.post("/me/api-keys/does-not-exist/revoke", headers=_auth(raw_a))

    assert kb.id not in listing.text
    assert response.status_code == 404
    assert response.json() == missing.json() == {"detail": "not found"}
    assert env.client.get("/me/api-keys", headers=_auth(raw_b)).status_code == 200
    assert env.actions() == []


def test_audit_rows_carry_no_secrets(env) -> None:
    tenant, [(k1, raw1)] = env.tenant_with_keys("A", 1)
    created = env.client.post("/me/api-keys", headers=_auth(raw1)).json()
    env.client.post(f"/me/api-keys/{created['id']}/revoke", headers=_auth(raw1))

    entries = env.audit.list_entries(100, 0)[0]

    assert {e.action for e in entries} == {"api_key.self_create", "api_key.self_revoke"}
    assert all(e.target_tenant_id == tenant.id for e in entries)
    dump = repr(entries)
    for secret in (raw1, created["api_key"], created["id"], k1.id):
        assert secret not in dump


@pytest.mark.parametrize(
    ("method", "path"),
    [("get", "/me/api-keys"), ("post", "/me/api-keys"), ("post", "/me/api-keys/x/revoke")],
)
def test_no_invalid_or_operator_auth_is_401(env, method, path) -> None:
    env.tenant_with_keys("A", 1)
    call = getattr(env.client, method)

    assert call(path).status_code == 401
    assert call(path, headers=_auth("bogus")).status_code == 401
    assert call(path, headers={"X-Operator-Token": "the-real-operator-token"}).status_code == 401
    assert call(path, headers=_auth("the-real-operator-token")).status_code == 401
