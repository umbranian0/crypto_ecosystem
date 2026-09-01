"""GW-021: `app.dependencies.operator_auth.get_authenticated_operator`.

Exercises the dependency through a minimal FastAPI test route, the same
"minimal test app" pattern `test_auth.py` (GW-006) already uses for
`get_authenticated_tenant` before a real router existed to test through.

Test acceptance criteria covered:
- valid `OPERATOR_TOKEN` -> 200
- missing/wrong token -> 401
- a real tenant's own valid API key, presented as `X-Operator-Token` (or
  against `get_authenticated_tenant` with an operator token), never
  satisfies the other dependency -- the cross-boundary case this ticket
  exists to close
- the raw token value never appears in any captured log line
"""

from __future__ import annotations

import hashlib
import logging

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.operator_auth import get_authenticated_operator
from app.dependencies.repositories import get_api_key_repository

OPERATOR_TOKEN = "the-real-operator-token"
TENANT_RAW_KEY = "tenant-a-real-api-key"
TENANT_ID = "tenant-a"


def _operator_client() -> TestClient:
    app = FastAPI()

    @app.get("/operator-only")
    def operator_only(_operator=Depends(get_authenticated_operator)):
        return {"ok": True}

    return TestClient(app)


def test_valid_operator_token_returns_200(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    client = _operator_client()

    response = client.get("/operator-only", headers={"X-Operator-Token": OPERATOR_TOKEN})

    assert response.status_code == 200
    assert response.json() == {"ok": True}


def test_missing_token_returns_401(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    client = _operator_client()

    response = client.get("/operator-only")

    assert response.status_code == 401


def test_wrong_token_returns_401(monkeypatch) -> None:
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    client = _operator_client()

    response = client.get("/operator-only", headers={"X-Operator-Token": "not-the-real-token"})

    assert response.status_code == 401


def test_unset_operator_token_env_var_returns_401(monkeypatch) -> None:
    monkeypatch.delenv("OPERATOR_TOKEN", raising=False)
    client = _operator_client()

    response = client.get("/operator-only", headers={"X-Operator-Token": "anything"})

    assert response.status_code == 401


def test_operator_token_read_at_call_time_not_memoized_at_import(monkeypatch) -> None:
    """Proves the env var is read fresh per-request (ticket AC), not
    captured once at module import -- flips the value mid-test and checks
    the dependency picks up the new value on the very next call.
    """
    monkeypatch.setenv("OPERATOR_TOKEN", "first-token")
    client = _operator_client()

    first = client.get("/operator-only", headers={"X-Operator-Token": "first-token"})
    assert first.status_code == 200

    monkeypatch.setenv("OPERATOR_TOKEN", "second-token")

    stale = client.get("/operator-only", headers={"X-Operator-Token": "first-token"})
    assert stale.status_code == 401

    fresh = client.get("/operator-only", headers={"X-Operator-Token": "second-token"})
    assert fresh.status_code == 200


class _FakeApiKeyRepository:
    def __init__(self, records_by_hash):
        self.records_by_hash = records_by_hash

    def create_key(self, tenant_id, key_hash):  # pragma: no cover
        raise NotImplementedError

    def get_by_hash(self, key_hash):
        return self.records_by_hash.get(key_hash)

    def revoke_key(self, tenant_id, key_id):  # pragma: no cover
        raise NotImplementedError


def _make_tenant_key_record(tenant_id: str, raw_key: str):
    from datetime import datetime, timezone

    from app.repositories.interfaces import ApiKeyRecord

    return ApiKeyRecord(
        id="key-1",
        tenant_id=tenant_id,
        key_hash=hashlib.sha256(raw_key.encode()).hexdigest(),
        created_at=datetime.now(timezone.utc),
        revoked_at=None,
    )


def _combined_client(repo) -> TestClient:
    app = FastAPI()

    @app.get("/operator-only")
    def operator_only(_operator=Depends(get_authenticated_operator)):
        return {"ok": True}

    @app.get("/tenant-only")
    def tenant_only(tenant=Depends(get_authenticated_tenant)):
        return {"tenant_id": tenant.tenant_id}

    app.dependency_overrides[get_api_key_repository] = lambda: repo
    return TestClient(app)


def test_tenant_api_key_presented_as_operator_token_is_rejected(monkeypatch) -> None:
    """The cross-boundary case this ticket exists to close: a real, valid
    tenant API key must never satisfy `get_authenticated_operator`, even
    when `OPERATOR_TOKEN` happens to be set to something else entirely.
    """
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    repo = _FakeApiKeyRepository(
        {hashlib.sha256(TENANT_RAW_KEY.encode()).hexdigest(): _make_tenant_key_record(TENANT_ID, TENANT_RAW_KEY)}
    )
    client = _combined_client(repo)

    # Sanity check: the tenant key is in fact valid against tenant auth.
    tenant_response = client.get("/tenant-only", headers={"Authorization": f"Bearer {TENANT_RAW_KEY}"})
    assert tenant_response.status_code == 200
    assert tenant_response.json() == {"tenant_id": TENANT_ID}

    # The actual proof: presenting that same valid tenant key as the
    # operator header must be rejected.
    operator_response = client.get("/operator-only", headers={"X-Operator-Token": TENANT_RAW_KEY})
    assert operator_response.status_code == 401


def test_operator_token_presented_as_tenant_api_key_is_rejected(monkeypatch) -> None:
    """The reverse direction of the same cross-boundary guarantee: the
    operator token must not satisfy `get_authenticated_tenant` either.
    """
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    repo = _FakeApiKeyRepository({})
    client = _combined_client(repo)

    response = client.get("/tenant-only", headers={"Authorization": f"Bearer {OPERATOR_TOKEN}"})

    assert response.status_code == 401


def test_no_raw_operator_token_appears_in_any_captured_log_record(monkeypatch, caplog) -> None:
    """Mirrors GW-006/GW-014's own non-tautological log-capture discipline
    (`test_audit_logging.py`): a real `caplog` capture across both a
    successful and a failed attempt, asserting the actual raw token string
    used is absent from the actual rendered log output.
    """
    monkeypatch.setenv("OPERATOR_TOKEN", OPERATOR_TOKEN)
    client = _operator_client()
    wrong_token = "a-wrong-but-secret-looking-token"

    with caplog.at_level(logging.DEBUG):
        client.get("/operator-only", headers={"X-Operator-Token": OPERATOR_TOKEN})
        client.get("/operator-only", headers={"X-Operator-Token": wrong_token})
        client.get("/operator-only")

    rendered = " ".join(
        " ".join(str(value) for value in record.__dict__.values()) for record in caplog.records
    )

    assert OPERATOR_TOKEN not in rendered
    assert wrong_token not in rendered
