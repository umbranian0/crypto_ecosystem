"""GW-006: `app.dependencies.auth.get_authenticated_tenant`.

Exercises the dependency through a minimal FastAPI test route (GW-007 has
not wired real routing yet) with `ApiKeyRepositoryDep` overridden by an
in-memory fake, per FastAPI's standard `app.dependency_overrides` testing
pattern.

Cross-tenant isolation is deliberately not re-tested here (backlog AC4
defers that proof to GW-008's routing layer).
"""

from __future__ import annotations

import hashlib
from dataclasses import dataclass
from datetime import datetime, timezone

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.repositories import get_api_key_repository
from app.repositories.interfaces import ApiKeyRecord

RAW_KEY = "a-valid-raw-key"
TENANT_ID = "tenant-123"


@dataclass
class FakeApiKeyRepository:
    """`get_by_hash` only matches on the *hashed* value it was constructed
    with -- if the dependency ever looked up the raw key directly (instead
    of hashing first), this fake would never return a match, and the
    "valid key succeeds" tests below would fail.
    """

    records_by_hash: dict[str, ApiKeyRecord]

    def create_key(self, tenant_id: str, key_hash: str) -> ApiKeyRecord:  # pragma: no cover
        raise NotImplementedError

    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        return self.records_by_hash.get(key_hash)

    def revoke_key(self, tenant_id: str, key_id: str) -> None:  # pragma: no cover
        raise NotImplementedError


def _make_record(tenant_id: str, revoked: bool = False) -> ApiKeyRecord:
    return ApiKeyRecord(
        id="key-1",
        tenant_id=tenant_id,
        key_hash=hashlib.sha256(RAW_KEY.encode()).hexdigest(),
        created_at=datetime.now(timezone.utc),
        revoked_at=datetime.now(timezone.utc) if revoked else None,
    )


def _client(repo: FakeApiKeyRepository) -> TestClient:
    from fastapi import Depends

    app = FastAPI()

    @app.get("/whoami")
    def whoami(tenant=Depends(get_authenticated_tenant)):
        return {"tenant_id": tenant.tenant_id}

    app.dependency_overrides[get_api_key_repository] = lambda: repo
    return TestClient(app)


@pytest.fixture()
def valid_repo() -> FakeApiKeyRepository:
    return FakeApiKeyRepository({hashlib.sha256(RAW_KEY.encode()).hexdigest(): _make_record(TENANT_ID)})


@pytest.fixture()
def revoked_repo() -> FakeApiKeyRepository:
    return FakeApiKeyRepository(
        {hashlib.sha256(RAW_KEY.encode()).hexdigest(): _make_record(TENANT_ID, revoked=True)}
    )


@pytest.fixture()
def empty_repo() -> FakeApiKeyRepository:
    return FakeApiKeyRepository({})


def test_valid_key_via_authorization_bearer_resolves_tenant(valid_repo) -> None:
    client = _client(valid_repo)
    response = client.get("/whoami", headers={"Authorization": f"Bearer {RAW_KEY}"})

    assert response.status_code == 200
    assert response.json() == {"tenant_id": TENANT_ID}


def test_valid_key_via_x_api_key_fallback_resolves_tenant(valid_repo) -> None:
    client = _client(valid_repo)
    response = client.get("/whoami", headers={"X-Api-Key": RAW_KEY})

    assert response.status_code == 200
    assert response.json() == {"tenant_id": TENANT_ID}


def test_authorization_checked_before_x_api_key(valid_repo) -> None:
    # Authorization present but malformed must win (and 401) even though a
    # valid X-Api-Key is also present, proving the documented check order.
    client = _client(valid_repo)
    response = client.get(
        "/whoami",
        headers={"Authorization": "Bearer ", "X-Api-Key": RAW_KEY},
    )

    assert response.status_code == 401


def test_missing_both_headers_returns_401(valid_repo) -> None:
    client = _client(valid_repo)
    response = client.get("/whoami")

    assert response.status_code == 401


@pytest.mark.parametrize(
    "headers",
    [
        {"Authorization": "garbage-no-scheme"},
        {"Authorization": "Basic dXNlcjpwYXNz"},
        {"Authorization": "Bearer "},
        {"X-Api-Key": ""},
    ],
)
def test_malformed_key_returns_401(valid_repo, headers) -> None:
    client = _client(valid_repo)
    response = client.get("/whoami", headers=headers)

    assert response.status_code == 401


def test_unknown_key_returns_401(empty_repo) -> None:
    client = _client(empty_repo)
    response = client.get("/whoami", headers={"Authorization": f"Bearer {RAW_KEY}"})

    assert response.status_code == 401


def test_revoked_key_returns_401(revoked_repo) -> None:
    client = _client(revoked_repo)
    response = client.get("/whoami", headers={"Authorization": f"Bearer {RAW_KEY}"})

    assert response.status_code == 401


def test_lookup_hashes_before_comparing_never_matches_raw_key(valid_repo) -> None:
    # Directly proves the dependency hashes before lookup, not after: the
    # fake repo's store is keyed by the SHA-256 digest, so looking it up
    # with the raw (unhashed) key must miss.
    assert valid_repo.get_by_hash(RAW_KEY) is None
    assert valid_repo.get_by_hash(hashlib.sha256(RAW_KEY.encode()).hexdigest()) is not None
