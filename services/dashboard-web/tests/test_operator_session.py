"""DASH-113: `require_operator_session` dependency tests.

Mirrors `tests/test_downstream.py`'s non-tautological proof style (DASH-003):
a dummy test-only route is wired behind `RequireOperatorSessionDep` whose
body asserts `False` if reached, so a request only passes this test if that
body is *never executed*.

The cross-boundary test (`test_tenant_session_does_not_satisfy_operator_gate`)
is the case this ticket exists to close, mirroring GW-021's own analogous
test on the gateway-api side (ticket Test acceptance criteria).
"""

from __future__ import annotations

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.dependencies.operator_session import (
    RequireOperatorSessionDep,
    get_operator_session_store,
)
from app.dependencies.session import get_session_store

_probe_app = FastAPI()


@_probe_app.get("/__operator_probe__")
def _operator_probe_route(_: RequireOperatorSessionDep):
    assert False, "route body must never execute without a valid operator session"


@_probe_app.get("/__operator_probe_success__")
def _operator_probe_success_route(_: RequireOperatorSessionDep):
    return {"ok": True}


@pytest.fixture(autouse=True)
def _clear_sessions():
    yield
    get_operator_session_store()._sessions.clear()
    get_session_store()._sessions.clear()


def test_valid_operator_session_cookie_reaches_route_body() -> None:
    store = get_operator_session_store()
    session_id = store.create("some-operator-token")

    client = TestClient(_probe_app)
    client.cookies.set("operator_session_id", session_id)

    response = client.get("/__operator_probe_success__")

    assert response.status_code == 200


def test_missing_operator_cookie_redirects_before_route_body_runs() -> None:
    client = TestClient(_probe_app)

    response = client.get("/__operator_probe__", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_unknown_operator_session_id_redirects_before_route_body_runs() -> None:
    client = TestClient(_probe_app)
    client.cookies.set("operator_session_id", "not-a-real-operator-session-id")

    response = client.get("/__operator_probe__", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_tenant_session_does_not_satisfy_operator_gate() -> None:
    """A tenant's own DASH-002/003 `session_id` cookie must never satisfy
    `require_operator_session` -- the cross-boundary case this ticket exists
    to close.
    """
    tenant_store = get_session_store()
    tenant_session_id = tenant_store.create("some-tenant-api-key")

    client = TestClient(_probe_app)
    # Deliberately set the tenant's session id under the *operator* cookie
    # name too, to prove the store lookup -- not just the cookie name -- is
    # what rejects it: even if an attacker replayed a tenant session id as
    # the operator cookie's value, it resolves to nothing in the operator
    # store's separate namespace.
    client.cookies.set("operator_session_id", tenant_session_id)

    response = client.get("/__operator_probe__", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"
