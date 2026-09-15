"""GW-005: `scripts.provision_tenant.provision`, the testable core behind
`scripts/provision_tenant.py`'s CLI wrapper.

Asserts the ticket's binding requirements: a `tenants` row and an
`api_keys` row are created, the returned raw key hashes (SHA-256) to the
persisted `key_hash`, and the raw key is never itself equal to `key_hash`
(i.e. it was actually hashed, not stored as-is).

GW-030: also asserts `provision()`'s new synchronous, degraded-not-blocking
call to `ingestion-service`'s `POST /internal/seed-platform-history` --
fakes the downstream with `httpx.MockTransport` (same pattern
`test_operator_routing.py`/`test_downstream_failures.py` already use), proving
exactly one seed call is made with the real newly created tenant's id, a
transport failure (`httpx.ConnectError`) and a non-2xx response (`500`) are
both caught and logged as a structured `tenant_seed_degraded` warning without
raising, and `provision()`'s return value is unaffected either way.
"""

from __future__ import annotations

import hashlib
import logging
import sys
from pathlib import Path

import httpx
import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from provision_tenant import provision  # noqa: E402

from app.repositories.sqlite_repository import SQLiteApiKeyRepository, SQLiteTenantRepository

INTERNAL_TOKEN = "the-real-internal-token"


@pytest.fixture()
def db_path(tmp_path) -> str:
    return str(tmp_path / "gateway.db")


@pytest.fixture()
def tenant_repo(db_path) -> SQLiteTenantRepository:
    return SQLiteTenantRepository(db_path)


@pytest.fixture()
def key_repo(db_path) -> SQLiteApiKeyRepository:
    return SQLiteApiKeyRepository(db_path)


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://internal-ingestion-service.example",
    )


def test_provision_creates_tenant_and_api_key_with_correctly_hashed_key(
    tenant_repo, key_repo
) -> None:
    def _seed_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"row_counts": {}})

    tenant, raw_key = provision("Acme Corp", tenant_repo, key_repo, _mock_client(_seed_handler))

    fetched_tenant = tenant_repo.get_tenant(tenant.id)
    assert fetched_tenant is not None
    assert fetched_tenant.name == "Acme Corp"

    expected_hash = hashlib.sha256(raw_key.encode()).hexdigest()
    persisted_key = key_repo.get_by_hash(expected_hash)

    assert persisted_key is not None
    assert persisted_key.tenant_id == tenant.id
    assert persisted_key.key_hash == expected_hash
    assert raw_key != persisted_key.key_hash


def test_provision_triggers_exactly_one_seed_call_with_the_real_new_tenant_id(
    tenant_repo, key_repo, monkeypatch
) -> None:
    monkeypatch.setenv("INGESTION_INTERNAL_TOKEN", INTERNAL_TOKEN)
    captured_requests = []

    def _handler(request: httpx.Request) -> httpx.Response:
        captured_requests.append(request)
        return httpx.Response(200, json={"row_counts": {"price": 10}})

    tenant, _raw_key = provision("Acme Corp", tenant_repo, key_repo, _mock_client(_handler))

    assert len(captured_requests) == 1
    request = captured_requests[0]
    assert request.url.path == "/internal/seed-platform-history"
    assert request.headers["x-internal-token"] == INTERNAL_TOKEN
    assert httpx.Request("POST", request.url).method == "POST"
    import json

    assert json.loads(request.content) == {"tenant_id": tenant.id}


def test_provision_survives_downstream_connect_error_without_raising_or_changing_return_value(
    tenant_repo, key_repo, caplog
) -> None:
    def _connect_error_handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    with caplog.at_level(logging.WARNING):
        tenant, raw_key = provision(
            "Acme Corp", tenant_repo, key_repo, _mock_client(_connect_error_handler)
        )

    assert tenant is not None
    assert raw_key

    degraded_records = [
        record
        for record in caplog.records
        if getattr(record, "event_type", None) == "tenant_seed_degraded"
    ]
    assert len(degraded_records) == 1
    assert degraded_records[0].outcome == "degraded"
    assert degraded_records[0].tenant_id == tenant.id


def test_provision_survives_downstream_500_response_without_raising_or_changing_return_value(
    tenant_repo, key_repo, caplog
) -> None:
    def _server_error_handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "boom"})

    with caplog.at_level(logging.WARNING):
        tenant, raw_key = provision(
            "Acme Corp", tenant_repo, key_repo, _mock_client(_server_error_handler)
        )

    assert tenant is not None
    assert raw_key

    degraded_records = [
        record
        for record in caplog.records
        if getattr(record, "event_type", None) == "tenant_seed_degraded"
    ]
    assert len(degraded_records) == 1
    assert degraded_records[0].outcome == "degraded"
    assert degraded_records[0].tenant_id == tenant.id
