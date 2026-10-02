"""ADMIN-005-01: `mint_api_key`, `get_authenticated_key`, and SQLite's
`revoke_key_if_not_last_active` (the Postgres twin lives in
`test_postgres_repository.py`).
"""

from __future__ import annotations

import hashlib
import threading

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_authenticated_key
from app.dependencies.repositories import get_api_key_repository
from app.provisioning import mint_api_key
from app.repositories.sqlite_repository import SQLiteApiKeyRepository, SQLiteTenantRepository


@pytest.fixture()
def tenant_repo(db_path) -> SQLiteTenantRepository:
    return SQLiteTenantRepository(db_path)


@pytest.fixture()
def key_repo(db_path) -> SQLiteApiKeyRepository:
    return SQLiteApiKeyRepository(db_path)


def test_mint_api_key_persists_only_the_hash(tenant_repo, key_repo) -> None:
    tenant = tenant_repo.create_tenant("Acme")

    record, raw_key = mint_api_key(tenant.id, key_repo)

    assert record.key_hash == hashlib.sha256(raw_key.encode()).hexdigest()
    assert record.tenant_id == tenant.id
    assert key_repo.get_by_hash(record.key_hash) == record
    assert all(raw_key not in str(k) for k in key_repo.list_api_keys(tenant.id))


def test_get_authenticated_key_returns_the_matched_record(tenant_repo, key_repo) -> None:
    tenant = tenant_repo.create_tenant("Acme")
    record, raw_key = mint_api_key(tenant.id, key_repo)

    app = FastAPI()

    @app.get("/key")
    def key(found=Depends(get_authenticated_key)):
        return {"id": found.id, "tenant_id": found.tenant_id}

    app.dependency_overrides[get_api_key_repository] = lambda: key_repo
    response = TestClient(app).get("/key", headers={"Authorization": f"Bearer {raw_key}"})

    assert response.status_code == 200
    assert response.json() == {"id": record.id, "tenant_id": tenant.id}


def test_revoked_when_another_active_key_exists(tenant_repo, key_repo) -> None:
    tenant = tenant_repo.create_tenant("Acme")
    a, _ = mint_api_key(tenant.id, key_repo)
    mint_api_key(tenant.id, key_repo)

    assert key_repo.revoke_key_if_not_last_active(tenant.id, a.id) == "revoked"
    assert key_repo.get_by_hash(a.key_hash).revoked_at is not None


def test_last_active_key_is_refused_and_not_updated(tenant_repo, key_repo) -> None:
    tenant = tenant_repo.create_tenant("Acme")
    only, _ = mint_api_key(tenant.id, key_repo)

    assert key_repo.revoke_key_if_not_last_active(tenant.id, only.id) == "last_active"
    assert key_repo.get_by_hash(only.key_hash).revoked_at is None


def test_already_revoked_does_not_restamp(tenant_repo, key_repo) -> None:
    tenant = tenant_repo.create_tenant("Acme")
    a, _ = mint_api_key(tenant.id, key_repo)
    mint_api_key(tenant.id, key_repo)
    key_repo.revoke_key_if_not_last_active(tenant.id, a.id)
    first = key_repo.get_by_hash(a.key_hash).revoked_at

    assert key_repo.revoke_key_if_not_last_active(tenant.id, a.id) == "already_revoked"
    assert key_repo.get_by_hash(a.key_hash).revoked_at == first


def test_not_found_for_unknown_and_other_tenants_key(tenant_repo, key_repo) -> None:
    tenant_a = tenant_repo.create_tenant("A")
    tenant_b = tenant_repo.create_tenant("B")
    mint_api_key(tenant_a.id, key_repo)
    b_key, _ = mint_api_key(tenant_b.id, key_repo)
    mint_api_key(tenant_b.id, key_repo)

    assert key_repo.revoke_key_if_not_last_active(tenant_a.id, "no-such-key") == "not_found"
    assert key_repo.revoke_key_if_not_last_active(tenant_a.id, b_key.id) == "not_found"
    assert key_repo.get_by_hash(b_key.key_hash).revoked_at is None


def test_excluding_target_rule_ignores_already_revoked_keys(tenant_repo, key_repo) -> None:
    tenant = tenant_repo.create_tenant("Acme")
    a, _ = mint_api_key(tenant.id, key_repo)
    b, _ = mint_api_key(tenant.id, key_repo)
    c, _ = mint_api_key(tenant.id, key_repo)
    assert key_repo.revoke_key_if_not_last_active(tenant.id, a.id) == "revoked"
    assert key_repo.revoke_key_if_not_last_active(tenant.id, b.id) == "revoked"

    # a and b are revoked: c is the only active key, so it must be protected.
    assert key_repo.revoke_key_if_not_last_active(tenant.id, c.id) == "last_active"


def test_mutual_revoke_race_leaves_one_active_key(tenant_repo, key_repo) -> None:
    tenant = tenant_repo.create_tenant("Acme")
    a, _ = mint_api_key(tenant.id, key_repo)
    b, _ = mint_api_key(tenant.id, key_repo)
    barrier = threading.Barrier(2)
    outcomes: list[str] = []

    def revoke(key_id: str) -> None:
        barrier.wait()
        outcomes.append(key_repo.revoke_key_if_not_last_active(tenant.id, key_id))

    threads = [threading.Thread(target=revoke, args=(k.id,)) for k in (a, b)]
    [t.start() for t in threads]
    [t.join() for t in threads]

    assert sorted(outcomes) == ["last_active", "revoked"]
    assert sum(k.revoked_at is None for k in key_repo.list_api_keys(tenant.id)) == 1
