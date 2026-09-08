"""SETUP-003: `GET /`, `GET /setup`, `POST /setup` tests.

Fakes gateway-api with `httpx.MockTransport` (same pattern `test_auth.py`
already uses for `get_gateway_api_client`) -- no real network call.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.http_client import get_gateway_api_client
from app.main import app

RAW_KEY = "super-secret-tenant-api-key-do-not-leak"


class _RoutedTransport:
    def __init__(self, routes: dict[str, httpx.Response]) -> None:
        self.routes = routes
        self.calls: list[httpx.Request] = []

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.calls.append(request)
        key = f"{request.method} {request.url.path}"
        return self.routes[key]


def _make_client(transport: _RoutedTransport) -> TestClient:
    mock_client = httpx.Client(
        transport=httpx.MockTransport(transport.handler),
        base_url="http://gateway-api",
    )
    app.dependency_overrides[get_gateway_api_client] = lambda: mock_client
    return TestClient(app)


@pytest.fixture(autouse=True)
def _clear_overrides():
    yield
    app.dependency_overrides.clear()


def test_root_redirects_to_setup_when_not_initialized() -> None:
    transport = _RoutedTransport(
        {"GET /setup/status": httpx.Response(200, json={"initialized": False})}
    )
    client = _make_client(transport)

    response = client.get("/", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/setup"


def test_root_redirects_to_runs_when_initialized() -> None:
    transport = _RoutedTransport(
        {"GET /setup/status": httpx.Response(200, json={"initialized": True})}
    )
    client = _make_client(transport)

    response = client.get("/", follow_redirects=False)

    assert response.status_code in (302, 307)
    assert response.headers["location"] == "/runs"


def test_get_setup_renders_form_when_not_initialized() -> None:
    transport = _RoutedTransport(
        {"GET /setup/status": httpx.Response(200, json={"initialized": False})}
    )
    client = _make_client(transport)

    response = client.get("/setup")

    assert response.status_code == 200
    assert "form" in response.text
    assert 'action="/setup"' in response.text


def test_get_setup_redirects_to_login_when_already_initialized() -> None:
    transport = _RoutedTransport(
        {"GET /setup/status": httpx.Response(200, json={"initialized": True})}
    )
    client = _make_client(transport)

    response = client.get("/setup", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
    assert "error" not in response.text.lower()


def test_post_setup_success_shows_the_raw_key_once() -> None:
    transport = _RoutedTransport(
        {
            "POST /setup/initialize": httpx.Response(
                201,
                json={"tenant_id": "t-1", "tenant_name": "Acme Corp", "api_key": RAW_KEY},
            )
        }
    )
    client = _make_client(transport)

    response = client.post("/setup", data={"tenant_name": "Acme Corp"})

    assert response.status_code == 201
    assert RAW_KEY in response.text
    assert "Acme Corp" in response.text
    assert 'href="/login"' in response.text


def test_post_setup_when_already_initialized_redirects_gracefully() -> None:
    """SETUP-002's 409, reachable only via a direct POST (not the normal UI
    flow, since GET already redirects once initialized), must never surface
    as a raw error page.
    """
    transport = _RoutedTransport(
        {"POST /setup/initialize": httpx.Response(409, json={"detail": "already initialized"})}
    )
    client = _make_client(transport)

    response = client.post(
        "/setup", data={"tenant_name": "Acme Corp"}, follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_post_setup_empty_tenant_name_rejected_before_any_outbound_call() -> None:
    transport = _RoutedTransport({})
    client = _make_client(transport)

    response = client.post("/setup", data={"tenant_name": "   "})

    assert response.status_code == 422
    assert len(transport.calls) == 0


def test_raw_key_never_appears_in_a_redirect_location_header() -> None:
    transport = _RoutedTransport(
        {
            "POST /setup/initialize": httpx.Response(
                201,
                json={"tenant_id": "t-1", "tenant_name": "Acme Corp", "api_key": RAW_KEY},
            )
        }
    )
    client = _make_client(transport)

    response = client.post("/setup", data={"tenant_name": "Acme Corp"})

    assert RAW_KEY not in response.headers.get("location", "")


def test_setup_templates_have_no_banned_positioning_words() -> None:
    import pathlib

    templates_dir = pathlib.Path(__file__).parent.parent / "src" / "app" / "templates"
    for name in ("setup.html", "_setup_key_reveal.html", "setup_key_reveal.html"):
        text = (templates_dir / name).read_text(encoding="utf-8").lower()
        for banned in ("prediction", "forecast", "signal", "trading", "recommendation"):
            assert banned not in text, f"banned positioning word {banned!r} found in {name}"
