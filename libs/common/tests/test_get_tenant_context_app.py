"""App-level proof of get_tenant_context's fail-closed guarantee (LC-004).

Uses a minimal FastAPI test app defined here, standalone inside
libs/common/tests/ (no import from services/validation-service), so the
guarantee is proven against real FastAPI dependency-injection wiring rather
than by calling the resolver function directly (that's test_tenant_context.py's
job, LC-002/LC-003). See docs/tickets/LC-004.md Design.
"""

from __future__ import annotations

from fastapi import Depends, FastAPI
from fastapi.testclient import TestClient

from naive_first_common import TenantContext, get_tenant_context

app = FastAPI()


@app.get("/probe")
def probe(tenant: TenantContext = Depends(get_tenant_context)) -> dict[str, str]:
    return {"tenant_id": tenant.tenant_id}


@app.get("/probe-unreachable")
def probe_unreachable(tenant: TenantContext = Depends(get_tenant_context)) -> dict[str, str]:
    # Body must never execute on rejection; if it does, this fails the test
    # loudly (AssertionError) instead of the request just happening to be 401.
    raise AssertionError("handler body was invoked")


client = TestClient(app)


def test_valid_header_resolves_tenant_context_via_response() -> None:
    response = client.get("/probe", headers={"X-Tenant-Id": "tenant-123"})
    assert response.status_code == 200
    assert response.json() == {"tenant_id": "tenant-123"}


def test_missing_header_rejected_401_before_handler_runs() -> None:
    response = client.get("/probe-unreachable")
    assert response.status_code == 401


def test_empty_header_rejected_401_before_handler_runs() -> None:
    response = client.get("/probe-unreachable", headers={"X-Tenant-Id": ""})
    assert response.status_code == 401


def test_whitespace_header_rejected_401_before_handler_runs() -> None:
    response = client.get("/probe-unreachable", headers={"X-Tenant-Id": "   "})
    assert response.status_code == 401
