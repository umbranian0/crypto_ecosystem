"""SETUP-001: `GET /setup/status`.

Covers the ticket's three Test acceptance criteria: zero-tenant state,
>=1-tenant state (provisioned via the existing `provision()` fixture path,
`scripts/provision_tenant.py`'s testable core, same as `test_provisioning.py`
uses), and the response body having exactly the `initialized` key -- no
side-channel field. A fourth test proves no auth dependency is attached,
matching `test_system_health.py::test_no_auth_required`'s pattern for the
same claim on a sibling unauthenticated route.
"""

from __future__ import annotations

import sys
from pathlib import Path

from fastapi.testclient import TestClient

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from provision_tenant import provision  # noqa: E402

from app.dependencies.repositories import get_tenant_repository
from app.main import app
from app.repositories.sqlite_repository import SQLiteApiKeyRepository, SQLiteTenantRepository


class _FakeTenantRepository:
    def __init__(self, exists: bool) -> None:
        self._exists = exists

    def tenant_exists(self) -> bool:
        return self._exists

    def create_tenant(self, name: str):  # pragma: no cover - unused here
        raise NotImplementedError

    def get_tenant(self, tenant_id: str):  # pragma: no cover - unused here
        raise NotImplementedError


def _override(exists: bool) -> None:
    app.dependency_overrides[get_tenant_repository] = lambda: _FakeTenantRepository(exists)


def _clear_override() -> None:
    app.dependency_overrides.pop(get_tenant_repository, None)


def test_setup_status_reports_not_initialized_with_zero_tenants() -> None:
    _override(exists=False)
    try:
        response = TestClient(app).get("/setup/status")
    finally:
        _clear_override()

    assert response.status_code == 200
    assert response.json() == {"initialized": False}


def test_setup_status_reports_initialized_with_at_least_one_tenant() -> None:
    _override(exists=True)
    try:
        response = TestClient(app).get("/setup/status")
    finally:
        _clear_override()

    assert response.status_code == 200
    assert response.json() == {"initialized": True}


def test_setup_status_response_has_exactly_the_initialized_key() -> None:
    _override(exists=True)
    try:
        response = TestClient(app).get("/setup/status")
    finally:
        _clear_override()

    assert set(response.json().keys()) == {"initialized"}


def test_setup_status_requires_no_auth() -> None:
    _override(exists=False)
    try:
        response = TestClient(app).get("/setup/status")
    finally:
        _clear_override()

    assert response.status_code != 401


def test_setup_status_reflects_a_real_provisioned_tenant(tmp_path) -> None:
    """End-to-end: provisions a real tenant via `provision()` (the existing
    test-fixture path `test_provisioning.py` uses) into a real SQLite DB,
    then confirms `GET /setup/status` reflects it through the real
    `SQLiteTenantRepository`, not a fake.
    """
    db_path = str(tmp_path / "gateway.db")
    tenant_repo = SQLiteTenantRepository(db_path)
    key_repo = SQLiteApiKeyRepository(db_path)

    app.dependency_overrides[get_tenant_repository] = lambda: tenant_repo
    try:
        before = TestClient(app).get("/setup/status")
        assert before.json() == {"initialized": False}

        provision("Acme Corp", tenant_repo, key_repo)

        after = TestClient(app).get("/setup/status")
        assert after.json() == {"initialized": True}
    finally:
        app.dependency_overrides.pop(get_tenant_repository, None)
