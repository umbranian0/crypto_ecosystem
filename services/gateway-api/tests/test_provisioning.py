"""GW-005: `scripts.provision_tenant.provision`, the testable core behind
`scripts/provision_tenant.py`'s CLI wrapper.

Asserts the ticket's binding requirements: a `tenants` row and an
`api_keys` row are created, the returned raw key hashes (SHA-256) to the
persisted `key_hash`, and the raw key is never itself equal to `key_hash`
(i.e. it was actually hashed, not stored as-is).
"""

from __future__ import annotations

import hashlib
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from provision_tenant import provision  # noqa: E402

from app.repositories.sqlite_repository import SQLiteApiKeyRepository, SQLiteTenantRepository


@pytest.fixture()
def db_path(tmp_path) -> str:
    return str(tmp_path / "gateway.db")


@pytest.fixture()
def tenant_repo(db_path) -> SQLiteTenantRepository:
    return SQLiteTenantRepository(db_path)


@pytest.fixture()
def key_repo(db_path) -> SQLiteApiKeyRepository:
    return SQLiteApiKeyRepository(db_path)


def test_provision_creates_tenant_and_api_key_with_correctly_hashed_key(
    tenant_repo, key_repo
) -> None:
    tenant, raw_key = provision("Acme Corp", tenant_repo, key_repo)

    fetched_tenant = tenant_repo.get_tenant(tenant.id)
    assert fetched_tenant is not None
    assert fetched_tenant.name == "Acme Corp"

    expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    persisted_key = key_repo.get_by_hash(expected_hash)

    assert persisted_key is not None
    assert persisted_key.tenant_id == tenant.id
    assert persisted_key.key_hash == expected_hash
    assert raw_key != persisted_key.key_hash
