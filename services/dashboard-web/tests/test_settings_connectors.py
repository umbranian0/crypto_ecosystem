"""DASH-112: `GET /settings/connectors` tests.

Mocks gateway-api's `GET /ingestion/connectors/credentials-status` the same
way `tests/test_monitoring.py` mocks `GET /system/health` -- monkeypatching
`httpx.Client` itself, since this router builds `httpx.Client(base_url=...)`
per-request rather than depending on an injectable client (same established
pattern, reused not reinvented).

Operator-session setup mirrors `tests/test_operator_login.py`'s own
`get_operator_session_store()`/`operator_session_id` cookie convention -- a
tenant's own `session_id` cookie (DASH-002/003) is never read by this route's
gate, so a request carrying only that cookie must be redirected the same way
an unauthenticated request is.
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


def test_tenants_own_session_cannot_reach_settings_connectors() -> None:
    """The cross-boundary case this ticket exists to close: a tenant's own
    `session_id` cookie (DASH-002/003) must never satisfy this route's
    operator gate.
    """
    client = TestClient(app)
    client.cookies.set("session_id", "irrelevant-tenant-session-value")

    response = client.get("/settings/connectors", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_no_session_at_all_redirected_to_operator_login() -> None:
    client = TestClient(app)

    response = client.get("/settings/connectors", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_operator_session_no_tenant_id_renders_form_with_no_error_no_table() -> None:
    client = _operator_client()

    response = client.get("/settings/connectors")

    assert response.status_code == 200
    assert "Enter a tenant id." not in response.text
    assert "<table>" not in response.text


def test_operator_session_blank_tenant_id_shows_enter_tenant_id_error() -> None:
    client = _operator_client()

    response = client.get("/settings/connectors", params={"tenant_id": "   "})

    assert response.status_code == 422
    assert "Enter a tenant id." in response.text
    assert "<table>" not in response.text


def test_operator_session_valid_tenant_id_renders_status_table(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/connectors/credentials-status"
        assert request.url.params["tenant_id"] == "tenant-123"
        assert request.headers["x-operator-token"] == OPERATOR_TOKEN
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "source": "binance_price",
                        "credential_set": True,
                        "last_set_at": "2026-08-01T00:00:00Z",
                    },
                    {
                        "source": "reddit_vader_sentiment",
                        "credential_set": False,
                        "last_set_at": None,
                    },
                ]
            },
        )

    _patch_transport(monkeypatch, handler)
    client = _operator_client()

    response = client.get("/settings/connectors", params={"tenant_id": "tenant-123"})

    assert response.status_code == 200
    assert "binance_price" in response.text
    assert "reddit_vader_sentiment" in response.text
    assert "2026-08-01T00:00:00Z" in response.text
    assert "never" in response.text


def test_operator_session_unrecognized_tenant_id_renders_all_false_not_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "source": "reddit_vader_sentiment",
                        "credential_set": False,
                        "last_set_at": None,
                    }
                ]
            },
        )

    _patch_transport(monkeypatch, handler)
    client = _operator_client()

    response = client.get("/settings/connectors", params={"tenant_id": "unknown-tenant"})

    assert response.status_code == 200
    assert "reddit_vader_sentiment" in response.text
    assert "results currently unavailable" not in response.text


def test_settings_connectors_template_has_no_banned_positioning_words() -> None:
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "settings_connectors.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, (
            f"banned positioning word {banned!r} found in settings_connectors.html"
        )
