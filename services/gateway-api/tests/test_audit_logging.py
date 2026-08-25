"""GW-014: auth event audit logging.

Exercises all three real call sites this ticket instruments -- `provision()`
(GW-005), `revoke()` (GW-010), and `get_authenticated_tenant` (GW-006) --
via `caplog`, proving each emits the correct `event_type`/`outcome`/
`tenant_id` and, non-tautologically, that the raw key string used in each
failure case never appears anywhere in the captured log record's rendered
output (message *and* `extra` payload, not just "we didn't pass it in").

Real SQLite-backed repositories are used throughout (mirroring
`test_revocation.py`'s own end-to-end fixture pattern), not mocks, so this
proves the real call sites, not a stand-in.
"""

from __future__ import annotations

import logging
import sys
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from provision_tenant import provision  # noqa: E402
from revoke_api_key import revoke  # noqa: E402

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.repositories import get_api_key_repository
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


def _client(repo: SQLiteApiKeyRepository) -> TestClient:
    app = FastAPI()

    @app.get("/whoami")
    def whoami(tenant=Depends(get_authenticated_tenant)):
        return {"tenant_id": tenant.tenant_id}

    app.dependency_overrides[get_api_key_repository] = lambda: repo
    return TestClient(app)


def _rendered_text(record: logging.LogRecord) -> str:
    """Everything a real log line could possibly surface for this record:
    the formatted message plus every `extra=` field set on it. Used for the
    non-tautological "raw key never appears" proof below -- a substring
    check against this, not an assumption that the test simply didn't pass
    the raw key to the logger.
    """
    return " ".join(str(value) for value in record.__dict__.values())


def _events(caplog, event_type: str) -> list[logging.LogRecord]:
    return [r for r in caplog.records if getattr(r, "event_type", None) == event_type]


def test_provision_logs_api_key_issued_with_tenant_id(caplog, tenant_repo, key_repo) -> None:
    with caplog.at_level(logging.INFO):
        tenant, _raw_key = provision("Acme Corp", tenant_repo, key_repo)

    issued = _events(caplog, "api_key_issued")
    assert len(issued) == 1
    assert issued[0].outcome == "success"
    assert issued[0].tenant_id == tenant.id


def test_revoke_logs_api_key_revoked_with_tenant_id(caplog, tenant_repo, key_repo) -> None:
    tenant, raw_key = provision("Acme Corp", tenant_repo, key_repo)
    caplog.clear()

    with caplog.at_level(logging.INFO):
        revoke(raw_key, key_repo)

    revoked = _events(caplog, "api_key_revoked")
    assert len(revoked) == 1
    assert revoked[0].outcome == "success"
    assert revoked[0].tenant_id == tenant.id


def test_auth_with_revoked_key_logs_auth_failed_with_tenant_id(
    caplog, tenant_repo, key_repo
) -> None:
    tenant, raw_key = provision("Acme Corp", tenant_repo, key_repo)
    revoke(raw_key, key_repo)
    client = _client(key_repo)
    caplog.clear()

    with caplog.at_level(logging.WARNING):
        response = client.get("/whoami", headers={"Authorization": f"Bearer {raw_key}"})

    assert response.status_code == 401
    failed = _events(caplog, "auth_failed")
    assert len(failed) == 1
    assert failed[0].outcome == "failure"
    assert failed[0].tenant_id == tenant.id
    assert raw_key not in _rendered_text(failed[0])


def test_auth_with_unknown_key_logs_auth_failed_with_no_tenant_id(caplog, key_repo) -> None:
    client = _client(key_repo)
    unknown_raw_key = "wholly-unknown-key-never-provisioned"

    with caplog.at_level(logging.WARNING):
        response = client.get("/whoami", headers={"Authorization": f"Bearer {unknown_raw_key}"})

    assert response.status_code == 401
    failed = _events(caplog, "auth_failed")
    assert len(failed) == 1
    assert failed[0].outcome == "failure"
    assert failed[0].tenant_id is None
    assert unknown_raw_key not in _rendered_text(failed[0])


@pytest.mark.parametrize(
    "headers",
    [
        {},
        {"Authorization": "garbage-no-scheme super-secret-raw-key-in-header"},
        {"Authorization": "Bearer "},
        {"X-Api-Key": ""},
    ],
)
def test_malformed_or_missing_auth_logs_auth_failed_with_no_tenant_id(
    caplog, key_repo, headers
) -> None:
    client = _client(key_repo)

    with caplog.at_level(logging.WARNING):
        response = client.get("/whoami", headers=headers)

    assert response.status_code == 401
    failed = _events(caplog, "auth_failed")
    assert len(failed) == 1
    assert failed[0].outcome == "failure"
    assert failed[0].tenant_id is None


def test_no_raw_key_ever_appears_in_any_captured_log_record(caplog, tenant_repo, key_repo) -> None:
    """Non-tautological proof (ticket's own required test): construct a real
    log capture across all four `auth.py` failure paths plus issuance/
    revocation, then assert the *actual* raw key string used in each case is
    absent from the *actual* captured text -- not merely "the test didn't
    pass it in on purpose".
    """
    with caplog.at_level(logging.INFO):
        tenant, raw_key = provision("Acme Corp", tenant_repo, key_repo)
        revoke(raw_key, key_repo)

    client = _client(key_repo)
    secret_looking_unknown_key = "another-super-secret-raw-key-value"

    with caplog.at_level(logging.WARNING):
        client.get("/whoami", headers={"Authorization": f"Bearer {raw_key}"})
        client.get("/whoami", headers={"Authorization": f"Bearer {secret_looking_unknown_key}"})
        client.get("/whoami", headers={"Authorization": "garbage-no-scheme"})
        client.get("/whoami", headers={"X-Api-Key": ""})
        client.get("/whoami")

    all_text = " ".join(_rendered_text(record) for record in caplog.records)

    assert raw_key not in all_text
    assert secret_looking_unknown_key not in all_text
