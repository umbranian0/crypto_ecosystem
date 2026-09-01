"""Tests for `GET /connectors/credentials-status` (`INGEST-012`).

Mirrors `test_connectors_router.py`'s `app.dependency_overrides` pattern:
`FakeCredentialRepository` (`tests/fake_repository.py`) wired in directly,
no live Postgres. Proves the ticket's own test acceptance criteria: a
tenant with a stored Reddit credential shows `credential_set: true` plus a
real timestamp; a tenant with none shows `credential_set: false,
last_set_at: null` -- never a `404`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient

from fake_repository import FakeConnectorRecordRepository, FakeCredentialRepository


@pytest.fixture
def client(monkeypatch):
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.dependencies.repositories import get_connector_record_repository, get_credential_repository
    from app.main import app

    connector_repository = FakeConnectorRecordRepository()
    credential_repository = FakeCredentialRepository()

    app.dependency_overrides[get_connector_record_repository] = lambda: connector_repository
    app.dependency_overrides[get_credential_repository] = lambda: credential_repository
    try:
        yield TestClient(app), credential_repository
    finally:
        app.dependency_overrides.pop(get_connector_record_repository, None)
        app.dependency_overrides.pop(get_credential_repository, None)


def test_tenant_with_no_stored_credentials_returns_200_not_404(client) -> None:
    test_client, _credential_repo = client

    response = test_client.get("/connectors/credentials-status", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 200
    body = response.json()
    assert body == {
        "items": [{"source": "reddit_vader_sentiment", "credential_set": False, "last_set_at": None}]
    }


def test_tenant_with_stored_reddit_credential_shows_set_true_and_timestamp(client, monkeypatch) -> None:
    from app import credential_crypto as cc

    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", cc.generate_key().decode("utf-8"))
    test_client, credential_repo = client
    credential_repo.set_credentials(
        "tenant-a", "reddit_vader_sentiment", client_id="cid", client_secret="secret"
    )

    response = test_client.get("/connectors/credentials-status", headers={"X-Tenant-Id": "tenant-a"})

    assert response.status_code == 200
    body = response.json()
    assert len(body["items"]) == 1
    item = body["items"][0]
    assert item["source"] == "reddit_vader_sentiment"
    assert item["credential_set"] is True
    assert item["last_set_at"] is not None


def test_never_returns_decrypted_credential_value(client, monkeypatch) -> None:
    from app import credential_crypto as cc

    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", cc.generate_key().decode("utf-8"))
    test_client, credential_repo = client
    credential_repo.set_credentials(
        "tenant-a", "reddit_vader_sentiment", client_id="super-secret-id", client_secret="super-secret-value"
    )

    response = test_client.get("/connectors/credentials-status", headers={"X-Tenant-Id": "tenant-a"})

    assert "super-secret-id" not in response.text
    assert "super-secret-value" not in response.text
    assert "client_id" not in response.json()["items"][0]
    assert "client_secret" not in response.json()["items"][0]


def test_cross_tenant_isolation(client, monkeypatch) -> None:
    from app import credential_crypto as cc

    monkeypatch.setenv("INGESTION_CREDENTIAL_ENCRYPTION_KEY", cc.generate_key().decode("utf-8"))
    test_client, credential_repo = client
    credential_repo.set_credentials(
        "tenant-a", "reddit_vader_sentiment", client_id="cid", client_secret="secret"
    )

    response_a = test_client.get("/connectors/credentials-status", headers={"X-Tenant-Id": "tenant-a"})
    response_b = test_client.get("/connectors/credentials-status", headers={"X-Tenant-Id": "tenant-b"})

    assert response_a.json()["items"][0]["credential_set"] is True
    assert response_b.json()["items"][0]["credential_set"] is False


def test_missing_tenant_header_returns_401(client) -> None:
    test_client, _credential_repo = client

    response = test_client.get("/connectors/credentials-status")

    assert response.status_code == 401
