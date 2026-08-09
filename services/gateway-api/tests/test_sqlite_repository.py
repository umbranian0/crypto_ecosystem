"""GW-004: `SQLiteTenantRepository`/`SQLiteUserRepository`/
`SQLiteApiKeyRepository` against a real file-based SQLite DB.

AC4 (backlog, load-bearing for this ticket): revocation is a flag, not a
delete -- `test_revoke_key_sets_revoked_at_and_get_by_hash_still_resolves`
creates a key, revokes it, then calls `get_by_hash` again and asserts the
row is still returned, now with `revoked_at` set.

Tenant isolation: per GW-003's documented exceptions, `get_by_hash` and
`get_user_by_email` correctly have no tenant_id filter -- they resolve
identity across tenants by design. No other tenant-scoped read method exists
on these interfaces beyond `get_tenant`/`revoke_key`'s tenant_id argument
(there is no tenant-scoped list/get for users or keys yet), so this file's
isolation test proves the identity-lookup methods resolve regardless of
which tenant created the row, and separately proves `revoke_key` cannot
revoke another tenant's key.
"""

from __future__ import annotations

import pytest

from app.repositories.sqlite_repository import (
    SQLiteApiKeyRepository,
    SQLiteTenantRepository,
    SQLiteUserRepository,
)


@pytest.fixture()
def tenant_repo(db_path) -> SQLiteTenantRepository:
    return SQLiteTenantRepository(db_path)


@pytest.fixture()
def user_repo(db_path) -> SQLiteUserRepository:
    return SQLiteUserRepository(db_path)


@pytest.fixture()
def key_repo(db_path) -> SQLiteApiKeyRepository:
    return SQLiteApiKeyRepository(db_path)


def test_create_tenant_persists_and_is_retrievable(tenant_repo) -> None:
    created = tenant_repo.create_tenant("Acme Corp")

    assert created.id
    assert created.name == "Acme Corp"

    fetched = tenant_repo.get_tenant(created.id)
    assert fetched == created


def test_get_tenant_returns_none_for_unknown_id(tenant_repo) -> None:
    assert tenant_repo.get_tenant("no-such-tenant") is None


def test_create_user_persists_and_is_retrievable_by_email(tenant_repo, user_repo) -> None:
    tenant = tenant_repo.create_tenant("Acme Corp")

    created = user_repo.create_user(tenant.id, "alice@acme.example", "admin")

    assert created.id
    assert created.tenant_id == tenant.id
    assert created.role == "admin"

    fetched = user_repo.get_user_by_email("alice@acme.example")
    assert fetched == created


def test_get_user_by_email_returns_none_for_unknown_email(user_repo) -> None:
    assert user_repo.get_user_by_email("nobody@nowhere.example") is None


def test_create_key_persists_and_is_retrievable_by_hash(tenant_repo, key_repo) -> None:
    tenant = tenant_repo.create_tenant("Acme Corp")

    created = key_repo.create_key(tenant.id, "hash-abc123")

    assert created.id
    assert created.tenant_id == tenant.id
    assert created.key_hash == "hash-abc123"
    assert created.revoked_at is None

    fetched = key_repo.get_by_hash("hash-abc123")
    assert fetched == created


def test_get_by_hash_returns_none_for_unknown_hash(key_repo) -> None:
    assert key_repo.get_by_hash("no-such-hash") is None


def test_revoke_key_sets_revoked_at_and_get_by_hash_still_resolves(tenant_repo, key_repo) -> None:
    """AC4 (backlog): revocation is a flag, not a delete. A revoked key's
    hash must still resolve via `get_by_hash`, now with `revoked_at` set --
    not None, not a missing/deleted row.
    """
    tenant = tenant_repo.create_tenant("Acme Corp")
    created = key_repo.create_key(tenant.id, "hash-to-revoke")
    assert created.revoked_at is None

    key_repo.revoke_key(tenant.id, created.id)

    revoked = key_repo.get_by_hash("hash-to-revoke")
    assert revoked is not None
    assert revoked.id == created.id
    assert revoked.revoked_at is not None


def test_revoke_key_does_not_affect_other_tenants_key(tenant_repo, key_repo) -> None:
    tenant_a = tenant_repo.create_tenant("Tenant A")
    tenant_b = tenant_repo.create_tenant("Tenant B")
    key_a = key_repo.create_key(tenant_a.id, "hash-a")

    # tenant_b attempts to revoke tenant_a's key by its real id.
    key_repo.revoke_key(tenant_b.id, key_a.id)

    still_active = key_repo.get_by_hash("hash-a")
    assert still_active is not None
    assert still_active.revoked_at is None


def test_identity_lookups_resolve_regardless_of_tenant(tenant_repo, user_repo, key_repo) -> None:
    """Tenant-isolation test (backlog AC): two distinct tenants, each with
    its own user and key. `get_by_hash`/`get_user_by_email` correctly
    resolve regardless of which tenant created the row (GW-003's documented
    exception -- these two methods don't yet know the tenant). No other
    tenant-scoped read method exists on these interfaces beyond
    `get_tenant`/`revoke_key`'s tenant_id argument, so there is no
    additional method to test for cross-tenant leakage here.
    """
    tenant_a = tenant_repo.create_tenant("Tenant A")
    tenant_b = tenant_repo.create_tenant("Tenant B")

    user_a = user_repo.create_user(tenant_a.id, "a@example.com", "member")
    user_b = user_repo.create_user(tenant_b.id, "b@example.com", "member")
    key_a = key_repo.create_key(tenant_a.id, "hash-tenant-a")
    key_b = key_repo.create_key(tenant_b.id, "hash-tenant-b")

    fetched_user_a = user_repo.get_user_by_email("a@example.com")
    fetched_user_b = user_repo.get_user_by_email("b@example.com")
    assert fetched_user_a is not None and fetched_user_a.tenant_id == tenant_a.id
    assert fetched_user_b is not None and fetched_user_b.tenant_id == tenant_b.id

    fetched_key_a = key_repo.get_by_hash("hash-tenant-a")
    fetched_key_b = key_repo.get_by_hash("hash-tenant-b")
    assert fetched_key_a is not None and fetched_key_a.tenant_id == tenant_a.id
    assert fetched_key_b is not None and fetched_key_b.tenant_id == tenant_b.id

    # revoke_key is tenant-scoped: tenant_b cannot revoke tenant_a's key.
    key_repo.revoke_key(tenant_b.id, key_a.id)
    assert key_repo.get_by_hash("hash-tenant-a").revoked_at is None

    assert user_a.id != user_b.id
