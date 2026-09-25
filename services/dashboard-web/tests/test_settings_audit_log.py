"""ADMIN-002-02: `/settings/audit-log` tests.

Mocks gateway-api's `ADMIN-002-01` `GET /operator-audit-log` the same way
`tests/test_settings_tenants.py` mocks `SETUP-011`'s endpoints --
monkeypatching `httpx.Client` itself, since this router builds
`httpx.Client(base_url=...)` per-request rather than depending on an
injectable client (same established pattern, reused not reinvented).

Operator-session setup mirrors `tests/test_settings_tenants.py`'s own
`get_operator_session_store()`/`operator_session_id` cookie convention -- a
tenant's own `session_id` cookie is never read by this route's gate, so a
request carrying only that cookie must be redirected the same way an
unauthenticated request is.
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


def _audit_log_payload(**overrides) -> dict:
    payload = {
        "items": [
            {
                "id": "audit-1",
                "action": "tenant.created",
                "target_tenant_id": "tenant-1",
                "correlation_id": "corr-1",
                "at": "2026-09-20T00:00:00Z",
            },
            {
                "id": "audit-2",
                "action": "api_key.revoked",
                "target_tenant_id": "tenant-2",
                "correlation_id": "corr-2",
                "at": "2026-09-21T00:00:00Z",
            },
        ],
        "limit": 20,
        "offset": 0,
        "total": 2,
    }
    payload.update(overrides)
    return payload


def test_tenants_own_session_cannot_reach_settings_audit_log() -> None:
    client = TestClient(app)
    client.cookies.set("session_id", "irrelevant-tenant-session-value")

    response = client.get("/settings/audit-log", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_no_session_at_all_redirected_to_operator_login() -> None:
    client = TestClient(app)

    response = client.get("/settings/audit-log", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_settings_audit_log_renders_items(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/operator-audit-log"
        assert request.headers["x-operator-token"] == OPERATOR_TOKEN
        return httpx.Response(200, json=_audit_log_payload())

    _patch_transport(monkeypatch, handler)
    client = _operator_client()

    response = client.get("/settings/audit-log")

    assert response.status_code == 200
    for item in _audit_log_payload()["items"]:
        assert item["action"] in response.text
        assert item["target_tenant_id"] in response.text
        assert item["at"] in response.text
        assert item["correlation_id"] in response.text


def test_settings_audit_log_renders_dash_for_null_target_tenant_id(monkeypatch) -> None:
    payload = _audit_log_payload(
        items=[
            {
                "id": "audit-3",
                "action": "tenant.created",
                "target_tenant_id": None,
                "correlation_id": "corr-3",
                "at": "2026-09-22T00:00:00Z",
            }
        ],
        total=1,
    )

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    _patch_transport(monkeypatch, handler)
    client = _operator_client()

    response = client.get("/settings/audit-log")

    assert response.status_code == 200
    assert "—" in response.text
    assert "None" not in response.text
    assert "null" not in response.text


def test_settings_audit_log_forwards_limit_and_offset(monkeypatch) -> None:
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["limit"] = request.url.params.get("limit")
        captured["offset"] = request.url.params.get("offset")
        return httpx.Response(200, json=_audit_log_payload(limit=5, offset=10))

    _patch_transport(monkeypatch, handler)
    client = _operator_client()

    response = client.get("/settings/audit-log", params={"limit": 5, "offset": 10})

    assert response.status_code == 200
    assert captured["limit"] == "5"
    assert captured["offset"] == "10"


def test_settings_audit_log_has_no_mutating_controls() -> None:
    """Scans `settings_audit_log.html`'s own source, not the full rendered
    response body: `base.html`'s operator nav (shared by every `/settings/*`
    page) always renders its own pre-existing "Log out (operator)"
    `<form>`/`<button type="submit">` whenever an `operator_session_id`
    cookie is present -- that control belongs to `base.html`, is unrelated to
    this ticket's scope, and would make a whole-response-body scan fail for
    every operator-gated page in this service, not just this one. The
    Implementation acceptance criterion's own wording ("anywhere in
    `settings_audit_log.html`") is scoped to this ticket's own template file,
    which this test asserts directly.
    """
    from pathlib import Path

    templates_dir = Path(__file__).parent.parent / "src" / "app" / "templates"
    text = (templates_dir / "settings_audit_log.html").read_text(encoding="utf-8").lower()
    for banned in ("<form", "<button", "hx-post", "hx-delete"):
        assert banned not in text, f"mutating control {banned!r} found in settings_audit_log.html"


def test_settings_audit_log_partial_has_no_banned_positioning_words() -> None:
    from pathlib import Path

    templates_dir = Path(__file__).parent.parent / "src" / "app" / "templates"
    text = (templates_dir / "settings_audit_log.html").read_text(encoding="utf-8").lower()
    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in settings_audit_log.html"
