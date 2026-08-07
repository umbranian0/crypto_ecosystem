"""Tests for GW-003's repository interfaces.

Covers: no storage-driver import in interfaces.py, enforced mechanically via
AST inspection (not just by eye), the three Protocols being non-instantiable
directly, and a minimal fake implementation proving the declared method set
(including the three documented tenant_id-not-first exceptions) is actually
implementable end to end.
"""

from __future__ import annotations

import ast
import inspect
from datetime import datetime, timezone

import pytest

from app.repositories.interfaces import (
    ApiKeyRecord,
    ApiKeyRepository,
    TenantRecord,
    TenantRepository,
    UserRecord,
    UserRepository,
)

_FORBIDDEN_MODULE_ROOTS = {"sqlite3", "psycopg", "sqlalchemy"}


def _imported_module_roots(source: str) -> set[str]:
    tree = ast.parse(source)
    roots: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.Import):
            roots.update(alias.name.split(".")[0] for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            roots.add(node.module.split(".")[0])
    return roots


def test_interfaces_module_imports_no_storage_driver() -> None:
    source = inspect.getsource(inspect.getmodule(TenantRepository))

    roots = _imported_module_roots(source)

    assert roots.isdisjoint(_FORBIDDEN_MODULE_ROOTS), (
        f"interfaces.py must stay storage-driver-free; found forbidden "
        f"imports: {roots & _FORBIDDEN_MODULE_ROOTS}"
    )


def test_tenant_repository_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        TenantRepository()


def test_user_repository_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        UserRepository()


def test_api_key_repository_cannot_be_instantiated_directly() -> None:
    with pytest.raises(TypeError):
        ApiKeyRepository()


class _FakeTenantRepository:
    """Minimal in-memory implementation proving the interface is implementable."""

    def __init__(self) -> None:
        self._tenants: dict[str, TenantRecord] = {}
        self._next_id = 0

    def create_tenant(self, name: str) -> TenantRecord:
        self._next_id += 1
        record = TenantRecord(
            id=f"tenant-{self._next_id}",
            name=name,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self._tenants[record.id] = record
        return record

    def get_tenant(self, tenant_id: str) -> TenantRecord | None:
        return self._tenants.get(tenant_id)


class _FakeUserRepository:
    """Minimal in-memory implementation proving the interface is implementable."""

    def __init__(self) -> None:
        self._users_by_id: dict[tuple[str, str], UserRecord] = {}
        self._users_by_email: dict[str, UserRecord] = {}
        self._next_id = 0

    def create_user(self, tenant_id: str, email: str, role: str) -> UserRecord:
        self._next_id += 1
        record = UserRecord(
            id=f"user-{self._next_id}",
            tenant_id=tenant_id,
            email=email,
            role=role,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
        )
        self._users_by_id[(tenant_id, record.id)] = record
        self._users_by_email[email] = record
        return record

    def get_user_by_email(self, email: str) -> UserRecord | None:
        return self._users_by_email.get(email)


class _FakeApiKeyRepository:
    """Minimal in-memory implementation proving the interface is implementable."""

    def __init__(self) -> None:
        self._keys_by_hash: dict[str, ApiKeyRecord] = {}
        self._next_id = 0

    def create_key(self, tenant_id: str, key_hash: str) -> ApiKeyRecord:
        self._next_id += 1
        record = ApiKeyRecord(
            id=f"key-{self._next_id}",
            tenant_id=tenant_id,
            key_hash=key_hash,
            created_at=datetime.now(timezone.utc).replace(tzinfo=None),
            revoked_at=None,
        )
        self._keys_by_hash[key_hash] = record
        return record

    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        return self._keys_by_hash.get(key_hash)

    def revoke_key(self, tenant_id: str, key_id: str) -> None:
        for key_hash, record in list(self._keys_by_hash.items()):
            if record.tenant_id == tenant_id and record.id == key_id:
                self._keys_by_hash[key_hash] = ApiKeyRecord(
                    id=record.id,
                    tenant_id=record.tenant_id,
                    key_hash=record.key_hash,
                    created_at=record.created_at,
                    revoked_at=datetime.now(timezone.utc).replace(tzinfo=None),
                )


def test_fake_tenant_repository_satisfies_protocol_and_round_trips() -> None:
    repo: TenantRepository = _FakeTenantRepository()
    assert isinstance(repo, TenantRepository)

    tenant = repo.create_tenant("acme")
    assert repo.get_tenant(tenant.id) == tenant
    assert repo.get_tenant("other-tenant") is None


def test_fake_user_repository_satisfies_protocol_and_looks_up_by_email() -> None:
    repo: UserRepository = _FakeUserRepository()
    assert isinstance(repo, UserRepository)

    user = repo.create_user("tenant-1", "alice@example.com", "admin")
    assert repo.get_user_by_email("alice@example.com") == user
    assert repo.get_user_by_email("nobody@example.com") is None


def test_fake_api_key_repository_satisfies_protocol_and_looks_up_by_hash_and_revokes() -> None:
    repo: ApiKeyRepository = _FakeApiKeyRepository()
    assert isinstance(repo, ApiKeyRepository)

    key = repo.create_key("tenant-1", "hash-abc")
    assert repo.get_by_hash("hash-abc") == key
    assert repo.get_by_hash("nonexistent-hash") is None

    repo.revoke_key("tenant-1", key.id)
    revoked = repo.get_by_hash("hash-abc")
    assert revoked.revoked_at is not None
