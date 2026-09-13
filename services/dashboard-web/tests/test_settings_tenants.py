"""SETUP-012: `/settings/tenants` tests.

Mocks gateway-api's `SETUP-011` endpoints the same way
`tests/test_settings_connectors.py` mocks `GET /ingestion/connectors/
credentials-status` -- monkeypatching `httpx.Client` itself, since this
router builds `httpx.Client(base_url=...)` per-request rather than depending
on an injectable client (same established pattern, reused not reinvented).

Operator-session setup mirrors `tests/test_settings_connectors.py`'s own
`get_operator_session_store()`/`operator_session_id` cookie convention -- a
tenant's own `session_id` cookie (DASH-002/003) is never read by this
route's gate, so a request carrying only that cookie must be redirected the
same way an unauthenticated request is.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.operator_session import get_operator_session_store
from app.main import app

OPERATOR_TOKEN = "super-secret-operator-token"


@pytest.fixture(autouse=True)
def _clear_operator_sessions():
    yield
    get_operator_session_store()._sessions.clear()


def _operator_client() -> TestClient:
    client = TestClient(app)
    session_id = get_operator_session_store().create(OPERATOR_TOKEN)
    client.cookies.set("operator_session_id", session_id)
    return client


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_tenants_own_session_cannot_reach_settings_tenants() -> None:
    client = TestClient(app)
    client.cookies.set("session_id", "irrelevant-tenant-session-value")

    response = client.get("/settings/tenants", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_no_session_at_all_redirected_to_operator_login() -> None:
    client = TestClient(app)

    response = client.get("/settings/tenants", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_post_tenants_own_session_cannot_reach_route() -> None:
    client = TestClient(app)
    client.cookies.set("session_id", "irrelevant-tenant-session-value")

    response = client.post(
        "/settings/tenants", data={"tenant_name": "acme"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_revoke_own_session_cannot_reach_route() -> None:
    client = TestClient(app)
    client.cookies.set("session_id", "irrelevant-tenant-session-value")

    response = client.post(
        "/settings/tenants/tenant-1/api-keys/key-1/revoke", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def _tenants_list_payload() -> dict:
    return {
        "items": [
            {
                "id": "tenant-1",
                "name": "Acme",
                "created_at": "2026-08-01T00:00:00Z",
                "api_keys": [
                    {"id": "key-1", "created_at": "2026-08-01T00:00:00Z", "revoked_at": None}
                ],
            }
        ]
    }


def test_operator_session_list_renders(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/tenants"
        assert request.headers["x-operator-token"] == OPERATOR_TOKEN
        return httpx.Response(200, json=_tenants_list_payload())

    _patch_transport(monkeypatch, handler)
    client = _operator_client()

    response = client.get("/settings/tenants")

    assert response.status_code == 200
    assert "Acme" in response.text
    assert "key-1" in response.text
    assert "active" in response.text


def test_create_tenant_shows_raw_key_once_then_absent_on_followup_get(monkeypatch) -> None:
    raw_key = "raw-api-key-value-shown-once"

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path == "/tenants":
            assert request.headers["x-operator-token"] == OPERATOR_TOKEN
            return httpx.Response(
                201,
                json={"tenant_id": "tenant-2", "tenant_name": "NewCo", "api_key": raw_key},
            )
        if request.method == "GET" and request.url.path == "/tenants":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "tenant-2",
                            "name": "NewCo",
                            "created_at": "2026-08-01T00:00:00Z",
                            "api_keys": [
                                {
                                    "id": "key-2",
                                    "created_at": "2026-08-01T00:00:00Z",
                                    "revoked_at": None,
                                }
                            ],
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    _patch_transport(monkeypatch, handler)
    client = _operator_client()

    create_response = client.post("/settings/tenants", data={"tenant_name": "NewCo"})

    assert create_response.status_code == 200
    assert raw_key in create_response.text
    assert "NewCo" in create_response.text

    followup_response = client.get("/settings/tenants")

    assert followup_response.status_code == 200
    assert raw_key not in followup_response.text
    assert "NewCo" in followup_response.text


def test_create_tenant_blank_name_shows_error_not_call(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "GET"
        assert request.url.path == "/tenants"
        return httpx.Response(200, json=_tenants_list_payload())

    _patch_transport(monkeypatch, handler)
    client = _operator_client()

    response = client.post("/settings/tenants", data={"tenant_name": "   "})

    assert response.status_code == 422
    assert "Enter a tenant name." in response.text


def test_revoke_updates_fragment_and_followup_get(monkeypatch) -> None:
    state = {"revoked": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST" and request.url.path.endswith("/revoke"):
            state["revoked"] = True
            return httpx.Response(
                200,
                json={
                    "tenant_id": "tenant-1",
                    "key_id": "key-1",
                    "revoked_at": "2026-09-13T00:00:00Z",
                },
            )
        if request.method == "GET" and request.url.path == "/tenants":
            revoked_at = "2026-09-13T00:00:00Z" if state["revoked"] else None
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "id": "tenant-1",
                            "name": "Acme",
                            "created_at": "2026-08-01T00:00:00Z",
                            "api_keys": [
                                {
                                    "id": "key-1",
                                    "created_at": "2026-08-01T00:00:00Z",
                                    "revoked_at": revoked_at,
                                }
                            ],
                        }
                    ]
                },
            )
        raise AssertionError(f"unexpected request {request.method} {request.url.path}")

    _patch_transport(monkeypatch, handler)
    client = _operator_client()

    revoke_response = client.post("/settings/tenants/tenant-1/api-keys/key-1/revoke")

    assert revoke_response.status_code == 200
    assert "2026-09-13T00:00:00Z" in revoke_response.text

    followup_response = client.get("/settings/tenants")

    assert followup_response.status_code == 200
    assert "2026-09-13T00:00:00Z" in followup_response.text


def test_settings_tenants_templates_have_no_banned_positioning_words() -> None:
    from pathlib import Path

    templates_dir = Path(__file__).parent.parent / "src" / "app" / "templates"
    for name in ("settings_tenants.html", "_one_time_reveal.html"):
        text = (templates_dir / name).read_text(encoding="utf-8").lower()
        for banned in ("prediction", "forecast", "signal", "recommendation"):
            assert banned not in text, f"banned positioning word {banned!r} found in {name}"
