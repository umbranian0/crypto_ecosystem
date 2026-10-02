"""ADMIN-005-03: `/api-keys` tests (gateway `/me/api-keys` mocked via httpx.MockTransport)."""

from __future__ import annotations

import re
from pathlib import Path

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.operator_session import get_operator_session_store
from app.dependencies.session import get_session_store
from app.main import app

SESSION_KEY = "tenant-session-raw-key"
MINTED_KEY = "freshly-minted-raw-key-value"
ITEMS = [
    {"id": "k-current", "created_at": "2026-10-01T10:00:00Z", "revoked_at": None, "current": True},
    {"id": "k-other", "created_at": "2026-10-01T11:00:00Z", "revoked_at": None, "current": False},
    {
        "id": "k-old",
        "created_at": "2026-09-01T11:00:00Z",
        "revoked_at": "2026-09-30T00:00:00Z",
        "current": False,
    },
]


@pytest.fixture(autouse=True)
def _clear_sessions():
    yield
    get_session_store()._sessions.clear()
    get_operator_session_store()._sessions.clear()


def _tenant_client() -> TestClient:
    client = TestClient(app)
    client.cookies.set("session_id", get_session_store().create(SESSION_KEY))
    return client


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


def _list_handler(request: httpx.Request) -> httpx.Response:
    assert request.headers["Authorization"] == f"Bearer {SESSION_KEY}"
    return httpx.Response(200, json={"items": ITEMS})


def test_no_session_redirects_to_login() -> None:
    for method in ("get", "post"):
        response = getattr(TestClient(app), method)("/api-keys", follow_redirects=False)
        assert response.status_code == 303
        assert response.headers["location"] == "/login"
    response = TestClient(app).post("/api-keys/k-other/revoke", follow_redirects=False)
    assert response.headers["location"] == "/login"


def test_operator_session_alone_cannot_satisfy_gate() -> None:
    client = TestClient(app)
    client.cookies.set(
        "operator_session_id", get_operator_session_store().create("operator-token")
    )

    response = client.get("/api-keys", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_list_renders_rows_and_disables_current_key(monkeypatch) -> None:
    _patch_transport(monkeypatch, _list_handler)

    response = _tenant_client().get("/api-keys")

    assert response.status_code == 200
    assert "k-current" in response.text and "k-other" in response.text and "k-old" in response.text
    assert "key in use by this session" in response.text
    assert "/api-keys/k-current/revoke" not in response.text
    assert "/api-keys/k-other/revoke" in response.text
    assert "/api-keys/k-old/revoke" not in response.text
    assert "2026-09-30T00:00:00Z" in response.text
    assert 'href="/api-keys"' in response.text


def test_mint_renders_reveal_with_no_store_and_key_not_persisted(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.method == "POST" and request.url.path == "/me/api-keys"
        return httpx.Response(
            201, json={"id": "k-new", "created_at": "2026-10-02T09:00:00Z", "api_key": MINTED_KEY}
        )

    _patch_transport(monkeypatch, handler)

    response = _tenant_client().post("/api-keys", follow_redirects=False)

    assert response.status_code == 200
    assert MINTED_KEY in response.text
    assert 'class="key-reveal"' in response.text
    assert "Back to My API Keys" in response.text
    assert response.headers["cache-control"] == "no-store"
    assert "location" not in response.headers
    assert MINTED_KEY not in get_session_store()._sessions.values()


def test_revoke_returns_row_fragment(monkeypatch) -> None:
    state = {"revoked": False}

    def handler(request: httpx.Request) -> httpx.Response:
        if request.method == "POST":
            assert request.url.path == "/me/api-keys/k-other/revoke"
            state["revoked"] = True
            return httpx.Response(200, json={"key_id": "k-other", "revoked_at": "2026-10-02T09:00:00Z"})
        items = [dict(i) for i in ITEMS]
        if state["revoked"]:
            items[1]["revoked_at"] = "2026-10-02T09:00:00Z"
        return httpx.Response(200, json={"items": items})

    _patch_transport(monkeypatch, handler)

    response = _tenant_client().post("/api-keys/k-other/revoke")

    assert response.status_code == 200
    assert 'id="api-key-row-k-other"' in response.text
    assert "2026-10-02T09:00:00Z" in response.text
    assert "<html" not in response.text
    assert "/revoke" not in response.text


@pytest.mark.parametrize(
    "status,detail,expected",
    [
        (404, "not found", "not found"),
        (409, "cannot revoke the key authenticating this request", "in use by your current session"),
        (409, "cannot revoke the last active key", "last active key"),
    ],
)
def test_revoke_404_409_render_inline_message(monkeypatch, status, detail, expected) -> None:
    _patch_transport(
        monkeypatch, lambda request: httpx.Response(status, json={"detail": detail})
    )

    response = _tenant_client().post("/api-keys/k-x/revoke")

    assert response.status_code == 200
    assert expected in response.text
    assert "Traceback" not in response.text


@pytest.mark.parametrize(
    "method,path", [("get", "/api-keys"), ("post", "/api-keys"), ("post", "/api-keys/k/revoke")]
)
def test_downstream_401_redirects_to_login(monkeypatch, method, path) -> None:
    _patch_transport(monkeypatch, lambda request: httpx.Response(401, json={"detail": "x"}))

    response = getattr(_tenant_client(), method)(path, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_new_templates_contain_no_banned_positioning_words() -> None:
    templates_dir = Path(__file__).resolve().parents[1] / "src" / "app" / "templates"
    banned = re.compile(r"\b(predict\w*|forecast\w*|signal\w*|recommend\w*|alpha|trading)\b", re.I)
    for name in ("api_keys.html", "_api_key_row.html", "_api_key_created.html",
                 "_api_key_revoke_error.html"):
        assert not banned.search((templates_dir / name).read_text(encoding="utf-8")), name
