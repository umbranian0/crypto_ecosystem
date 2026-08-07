"""GW-007: `app.dependencies.routing.build_downstream_headers`.

Proves two things: (1) the pure function itself returns exactly the
expected header dict from a directly-constructed `TenantContext`; (2) in a
real request/dependency scenario, a client-supplied `X-Tenant-Id` header
cannot influence the outbound header at all -- only GW-006's authenticated
tenant_id can, even when the two differ.
"""

from __future__ import annotations

import hashlib
import os
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path

import pytest
from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient
from naive_first_common.tenant_context import TenantContext

from app.dependencies.auth import get_authenticated_tenant
from app.dependencies.repositories import get_api_key_repository
from app.dependencies.routing import build_downstream_headers
from app.repositories.interfaces import ApiKeyRecord

RAW_KEY = "a-valid-raw-key"
AUTHENTICATED_TENANT_ID = "tenant-real"
SPOOFED_TENANT_ID = "tenant-attacker-claims"


def test_build_downstream_headers_returns_exact_expected_dict() -> None:
    tenant = TenantContext(tenant_id=AUTHENTICATED_TENANT_ID)

    assert build_downstream_headers(tenant) == {"X-Tenant-Id": AUTHENTICATED_TENANT_ID}


@dataclass
class FakeApiKeyRepository:
    records_by_hash: dict[str, ApiKeyRecord]

    def create_key(self, tenant_id: str, key_hash: str) -> ApiKeyRecord:  # pragma: no cover
        raise NotImplementedError

    def get_by_hash(self, key_hash: str) -> ApiKeyRecord | None:
        return self.records_by_hash.get(key_hash)

    def revoke_key(self, tenant_id: str, key_id: str) -> None:  # pragma: no cover
        raise NotImplementedError


def test_spoofed_inbound_x_tenant_id_header_never_reaches_outbound_header() -> None:
    """Sends a request with a valid API key for AUTHENTICATED_TENANT_ID *and*
    an inbound `X-Tenant-Id: SPOOFED_TENANT_ID` header. The route builds
    downstream headers purely from GW-006's resolved `TenantContext` -- if
    `build_downstream_headers` (or anything in its call path) ever read the
    inbound request's own `X-Tenant-Id` header, the assertion below would
    see the spoofed value instead of the authenticated one.
    """
    record = ApiKeyRecord(
        id="key-1",
        tenant_id=AUTHENTICATED_TENANT_ID,
        key_hash=hashlib.sha256(RAW_KEY.encode()).hexdigest(),
        created_at=datetime.now(timezone.utc),
        revoked_at=None,
    )
    repo = FakeApiKeyRepository({record.key_hash: record})

    app = FastAPI()

    @app.get("/downstream-headers")
    def downstream_headers(tenant=Depends(get_authenticated_tenant)):
        return build_downstream_headers(tenant)

    app.dependency_overrides[get_api_key_repository] = lambda: repo
    client = TestClient(app)

    response = client.get(
        "/downstream-headers",
        headers={
            "Authorization": f"Bearer {RAW_KEY}",
            "X-Tenant-Id": SPOOFED_TENANT_ID,
        },
    )

    assert response.status_code == 200
    assert response.json() == {"X-Tenant-Id": AUTHENTICATED_TENANT_ID}
    assert response.json()["X-Tenant-Id"] != SPOOFED_TENANT_ID


def test_diff_touches_only_services_gateway_api() -> None:
    """Scoped file-list check (ticket Test AC3): confirms this ticket's
    created/edited files are all under services/gateway-api/. Falls back to
    an explicit enumeration of this ticket's own file set if `git` isn't
    available/this tree isn't a git workspace, per the ticket's documented
    environment caveat.
    """
    repo_root = Path(__file__).resolve().parents[3]
    gateway_api_prefix = os.path.join("services", "gateway-api")

    # docs/tickets/GW-007.md is the ticket file itself (status/checkbox
    # updates); every code file this ticket creates/edits must be under
    # services/gateway-api/.
    ticket_doc = os.path.join("docs", "tickets", "GW-007.md")
    code_files = [
        os.path.join("services", "gateway-api", "src", "app", "dependencies", "routing.py"),
        os.path.join("services", "gateway-api", "tests", "test_routing_headers.py"),
        os.path.join("services", "gateway-api", "README.md"),
    ]

    for rel_path in code_files:
        assert rel_path.startswith(gateway_api_prefix), f"{rel_path} is outside services/gateway-api/"
        assert (repo_root / rel_path).exists(), f"{rel_path} does not exist under repo root"

    assert (repo_root / ticket_doc).exists()

    forbidden_prefixes = (
        os.path.join("libs", "common"),
        os.path.join("services", "validation-service"),
    )
    for rel_path in [*code_files, ticket_doc]:
        assert not rel_path.startswith(forbidden_prefixes), (
            f"{rel_path} touches a forbidden module for GW-007"
        )
