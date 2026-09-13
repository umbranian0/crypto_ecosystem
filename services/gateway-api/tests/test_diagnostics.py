"""SETUP-021: `GET /diagnostics/recent-errors` (gateway-api).

Wires the real `app.main.app` (the module-level `recent_errors_handler`
singleton must actually be attached to the root logger for this test to be
meaningful, not a fresh handler instance).
"""

from __future__ import annotations

import hashlib
import logging

from fastapi.testclient import TestClient

from app.dependencies.repositories import get_api_key_repository
from app.main import app
from app.repositories.interfaces import ApiKeyRecord

OPERATOR_TOKEN = "the-real-operator-token"
TENANT_RAW_KEY = "tenant-a-real-api-key"


class _FakeApiKeyRepository:
    def __init__(self, records_by_hash=None):
        self.records_by_hash = records_by_hash or {}

    def create_key(self, tenant_id, key_hash):  # pragma: no cover
        raise NotImplementedError

    def get_by_hash(self, key_hash):
        return self.records_by_hash.get(key_hash)

    def revoke_key(self, tenant_id, key_id):  # pragma: no cover
        raise NotImplementedError


def _clear_overrides():
    app.dependency_overrides.pop(get_api_key_repository, None)


def test_unauthenticated_returns_401(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    app.dependency_overrides[get_api_key_repository] = lambda: _FakeApiKeyRepository()
    try:
        response = TestClient(app).get("/diagnostics/recent-errors")
        assert response.status_code == 401
    finally:
        _clear_overrides()


def test_real_tenant_api_key_returns_403(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    from datetime import datetime, timezone

    record = ApiKeyRecord(
        id="key-1",
        tenant_id="tenant-a",
        key_hash=hashlib.sha256(TENANT_RAW_KEY.encode()).hexdigest(),
        created_at=datetime.now(timezone.utc),
        revoked_at=None,
    )
    repo = _FakeApiKeyRepository({record.key_hash: record})
    app.dependency_overrides[get_api_key_repository] = lambda: repo
    try:
        response = TestClient(app).get(
            "/diagnostics/recent-errors", headers={"X-Operator-Token": TENANT_RAW_KEY}
        )
        assert response.status_code == 403
    finally:
        _clear_overrides()


def test_authenticated_returns_warning_records_but_not_info(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    app.dependency_overrides[get_api_key_repository] = lambda: _FakeApiKeyRepository()
    try:
        logger = logging.getLogger("app.test_diagnostics")
        logger.warning("a diagnosable warning for SETUP-021")
        logger.info("an info line that must never appear")

        response = TestClient(app).get(
            "/diagnostics/recent-errors", headers={"X-Operator-Token": OPERATOR_TOKEN}
        )

        assert response.status_code == 200
        messages = [item["message"] for item in response.json()["items"]]
        assert "a diagnosable warning for SETUP-021" in messages
        assert "an info line that must never appear" not in messages
    finally:
        _clear_overrides()
