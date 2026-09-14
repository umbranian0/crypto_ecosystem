"""SETUP-034: `base.html`'s two independent nav blocks.

Renders a real page (`GET /login`, unauthenticated route, so reachable
regardless of cookie state) with each of the four cookie-presence
combinations and asserts the tenant/operator nav blocks render
independently -- no `{% elif %}` chain that would suppress one when both
cookies are present.
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def _get(client: TestClient, tenant_session: bool, operator_session: bool):
    if tenant_session:
        client.cookies.set("session_id", "irrelevant-tenant-session-value")
    if operator_session:
        client.cookies.set("operator_session_id", "irrelevant-operator-session-value")
    return client.get("/login")


def test_neither_cookie_renders_no_nav_blocks() -> None:
    client = TestClient(app)

    response = _get(client, tenant_session=False, operator_session=False)

    assert response.status_code == 200
    assert 'class="main-nav operator-nav"' not in response.text
    assert 'action="/logout"' not in response.text
    assert 'action="/operator-logout"' not in response.text


def test_tenant_only_renders_tenant_nav_only() -> None:
    client = TestClient(app)

    response = _get(client, tenant_session=True, operator_session=False)

    assert response.status_code == 200
    assert 'action="/logout"' in response.text
    assert 'action="/operator-logout"' not in response.text
    assert 'class="main-nav operator-nav"' not in response.text


def test_operator_only_renders_operator_nav_only() -> None:
    client = TestClient(app)

    response = _get(client, tenant_session=False, operator_session=True)

    assert response.status_code == 200
    assert 'action="/operator-logout"' in response.text
    assert 'class="main-nav operator-nav"' in response.text
    assert 'action="/logout"' not in response.text


def test_both_cookies_render_both_nav_blocks_simultaneously() -> None:
    client = TestClient(app)

    response = _get(client, tenant_session=True, operator_session=True)

    assert response.status_code == 200
    assert 'action="/logout"' in response.text
    assert 'action="/operator-logout"' in response.text
    assert 'class="main-nav operator-nav"' in response.text


def test_skip_to_main_content_link_is_first_focusable_element() -> None:
    """UAT-012: skip link precedes any nav link and targets the main landmark."""
    client = TestClient(app)

    response = _get(client, tenant_session=True, operator_session=True)

    assert response.status_code == 200
    skip_link_index = response.text.index('href="#main-content"')
    first_nav_link_index = response.text.index("<nav")
    assert skip_link_index < first_nav_link_index
    assert 'class="skip-link"' in response.text
    assert 'id="main-content"' in response.text


def test_operator_nav_links_present() -> None:
    client = TestClient(app)

    response = _get(client, tenant_session=False, operator_session=True)

    assert response.status_code == 200
    assert 'href="/settings/tenants"' in response.text
    assert 'href="/settings/environment"' in response.text
    assert 'href="/monitoring"' in response.text
