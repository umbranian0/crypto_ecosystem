"""GW-010: `scripts.revoke_api_key.revoke`, its `UnknownApiKeyError` path,
and the end-to-end proof that a revoked key fails GW-006's auth check on the
very next request (AC2 -- no caching window).

Unit tests reuse `test_auth.py`'s in-memory `FakeApiKeyRepository` shape
(dataclass, `records_by_hash: dict[str, ApiKeyRecord]`), extended here with a
working `revoke_key` implementation (that fake's own `revoke_key` raises
`NotImplementedError` since GW-006's auth path never calls it) -- this is not
a second, divergent fake-repo pattern, just this test file's own copy sized
for what this ticket's tests actually exercise, matching that file's own
per-test-module fake-repo convention (no shared fake-repo fixture exists in
`conftest.py` to import instead, confirmed by reading it first).

The end-to-end test provisions via `provision_tenant.provision` (real
SQLite-backed repositories, mirroring `test_provisioning.py`'s own db_path/
tenant_repo/key_repo fixture pattern) and imports `get_authenticated_tenant`
as-is (GW-006, not reimplemented) to prove AC2 against the real dependency,
not a stand-in.
"""

from __future__ import annotations

import hashlib
import sys
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from provision_tenant import provision  # noqa: E402
from revoke_api_key import UnknownApiKeyError, revoke  # noqa: E402

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord
from app.repositories.sqlite_repository import SQLiteApiKeyRepository, SQLiteTenantRepository

RAW_KEY = "a-valid-raw-key"
TENANT_ID = "tenant-123"


@dataclass
class FakeApiKeyRepository:
    """Same shape as `test_auth.py::FakeApiKeyRepository`, extended with a
    working `revoke_key` -- that file's fake raises `NotImplementedError`
    for `revoke_key` since GW-006's auth path never calls it, but this
    ticket's tests need it to actually mutate `records_by_hash`.
    """

    records_by_hash: dict[str, ApiKeyRecord] = field(default_factory=dict)
    revoke_calls: list[tuple[str, str]] = field(default_factory=list)

    def create_key(self, tenant_id: str, key_hash: str) -> ApiKeyRecord:  # pragma: no cover
        raise NotImplementedError

    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        return self.records_by_hash.get(key_hash)

    def revoke_key(self, tenant_id: str, key_id: str) -> None:
        self.revoke_calls.append((tenant_id, key_id))
        for stored_hash, record in list(self.records_by_hash.items()):
            if record.tenant_id == tenant_id and record.id == key_id:
                self.records_by_hash[stored_hash] = ApiKeyRecord(
                    id=record.id,
                    tenant_id=record.tenant_id,
                    key_hash=record.key_hash,
                    created_at=record.created_at,
                    revoked_at=datetime.now(timezone.utc),
                )


def _make_record(tenant_id: str, key_id: str = "key-1", revoked: bool = False) -> ApiKeyRecord:
    return ApiKeyRecord(
        id=key_id,
        tenant_id=tenant_id,
        key_hash=hashlib.sha256(RAW_KEY.encode()).hexdigest(),
        created_at=datetime.now(timezone.utc),
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )


def test_revoke_resolves_key_via_get_by_hash_and_calls_revoke_key_with_correct_ids() -> None:
    record = _make_record(TENANT_ID, key_id="key-1")
    repo = FakeApiKeyRepository({record.key_hash: record})

    revoked = revoke(RAW_KEY, repo)

    assert repo.revoke_calls == [(TENANT_ID, "key-1")]
    assert revoked.id == "key-1"
    assert revoked.tenant_id == TENANT_ID
    assert revoked.revoked_at is not None


def test_revoke_unknown_key_raises_clear_operator_error_not_stack_trace() -> None:
    repo = FakeApiKeyRepository({})

    with pytest.raises(UnknownApiKeyError):
        revoke("some-key-that-was-never-provisioned", repo)


def test_revoke_already_revoked_key_is_a_graceful_no_op() -> None:
    record = _make_record(TENANT_ID, key_id="key-1", revoked=True)
    repo = FakeApiKeyRepository({record.key_hash: record})

    revoked = revoke(RAW_KEY, repo)

    assert repo.revoke_calls == []  # revoke_key not called again
    assert revoked.revoked_at == record.revoked_at  # original timestamp preserved


def test_revoke_error_message_never_contains_the_raw_key() -> None:
    repo = FakeApiKeyRepository({})
    secret_raw_key = "super-secret-raw-key-value"

    with pytest.raises(UnknownApiKeyError) as excinfo:
        revoke(secret_raw_key, repo)

    assert secret_raw_key not in str(excinfo.value)


# --- End-to-end proof (the ticket's actual acceptance criteria) ---


@pytest.fixture()
def db_path(tmp_path) -> str:
    return str(tmp_path / "gateway.db")


@pytest.fixture()
def tenant_repo(db_path) -> SQLiteTenantRepository:
    return SQLiteTenantRepository(db_path)


@pytest.fixture()
def key_repo(db_path) -> SQLiteApiKeyRepository:
    return SQLiteApiKeyRepository(db_path)


def _client(repo: SQLiteApiKeyRepository) -> TestClient:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(tenant=Depends(get_authenticated_tenant)):
        return {"tenant_id": tenant.tenant_id}

    app.dependency_overrides[get_api_key_repository] = lambda: repo
    return TestClient(app)


def test_revoked_key_fails_auth_on_the_very_next_request_no_caching_window(
    tenant_repo, key_repo
) -> None:
    tenant, raw_key = provision("Acme Corp", tenant_repo, key_repo)
    client = _client(key_repo)

    ok_response = client.get("/whoami", headers={"Authorization": f"Bearer {raw_key}"})
    assert ok_response.status_code == 200
    assert ok_response.json() == {"tenant_id": tenant.id}

    revoke(raw_key, key_repo)

    revoked_response = client.get("/whoami", headers={"Authorization": f"Bearer {raw_key}"})
    assert revoked_response.status_code == 401


def test_revoke_api_key_script_defines_no_fastapi_router_or_route() -> None:
    # Grep-based proof (ticket's own suggested check) that this ticket's
    # script never becomes an HTTP-reachable path: no APIRouter/route
    # decorator anywhere in the file this ticket adds.
    script_path = Path(__file__).resolve().parents[1] / "scripts" / "revoke_api_key.py"
    source = script_path.read_text(encoding="utf-8")

    assert "APIRouter" not in source
    assert "@app." not in source
    assert "include_router" not in source
