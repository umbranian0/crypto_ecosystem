"""DASH-113: `GET /monitoring` tests.

Mocks gateway-api's `GET /system/health` (GW-022) the same way
`tests/test_runs_list.py` mocks `GET /runs` -- monkeypatching `httpx.Client`
itself, since this router builds `httpx.Client(base_url=...)` per-request
rather than depending on an injectable client (same established pattern,
reused not reinvented).

DASH-109: the "last crawl status" panel tests below reuse the exact same
`_patch_transport` monkeypatch (one fake `httpx.Client` handles every
outbound call the route makes -- `/system/health`, `/ingestion/datasets`,
`/ingestion/connectors/{source}/status` -- distinguished by `request.url.path`
in each test's own handler), and `app.dependencies.session.get_session_store`
to set a real tenant session cookie (`test_downstream.py`'s own established
pattern, not a new fixture shape) for the "populated"/"empty" cases; the
existing tests above set no cookie at all, proving the panel degrades to its
login-prompt state rather than the whole page redirecting.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "monitoring-test-raw-api-key"


@pytest.fixture(autouse=True)
def _clear_sessions():
    yield
    get_session_store()._sessions.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_monitoring_all_healthy(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system/health"
        return httpx.Response(
            200,
            json={
                "gateway-api": "ok",
                "validation-service": "ok",
                "reporting-service": "ok",
                "ingestion-service": "ok",
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "gateway-api" in response.text
    assert "validation-service" in response.text
    assert "reporting-service" in response.text
    assert "ingestion-service" in response.text
    assert response.text.count(">ok<") == 4


def test_monitoring_mixed_degraded_and_unreachable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "gateway-api": "ok",
                "validation-service": "degraded",
                "reporting-service": "unreachable",
                "ingestion-service": "ok",
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "degraded" in response.text
    assert "unreachable" in response.text


def test_monitoring_aggregate_call_transport_connect_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "connection refused" not in response.text


def test_monitoring_aggregate_call_transport_timeout(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text


def test_monitoring_non_200_from_gateway_api(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "internal error"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 500
    assert "results currently unavailable" in response.text
    assert "internal error" not in response.text


def test_monitoring_requires_no_session() -> None:
    """No cookie is set anywhere in this file -- matching GW-022's own
    no-auth design choice, `/monitoring` must not redirect an
    unauthenticated request.
    """
    client = TestClient(app)
    response = client.get("/monitoring", follow_redirects=False)

    assert response.status_code != 303


def test_monitoring_template_has_no_banned_positioning_words() -> None:
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "monitoring.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in monitoring.html"


# DASH-109: "last crawl status" panel


def _health_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "gateway-api": "ok",
            "validation-service": "ok",
            "reporting-service": "ok",
            "ingestion-service": "ok",
        },
    )


def test_monitoring_crawl_status_panel_shows_login_prompt_for_anonymous_visitor(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system/health"
        return _health_response()

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "Log in to view your own ingestion status" in response.text


def test_monitoring_crawl_status_panel_populated_for_logged_in_tenant(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "source": "binance_price_btcusdt_1h",
                            "earliest_timestamp": "2026-01-01T00:00:00",
                            "latest_timestamp": "2026-01-02T00:00:00",
                            "row_count": 24,
                        }
                    ]
                },
            )
        if request.url.path == "/ingestion/connectors/binance_price_btcusdt_1h/status":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "timestamp": "2026-01-02T00:00:00",
                    "row_count": 24,
                },
            )
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "binance_price_btcusdt_1h" in response.text
    assert "completed" in response.text
    assert "Log in to view your own ingestion status" not in response.text


def test_monitoring_crawl_status_panel_empty_for_logged_in_tenant_with_no_datasets(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": []})
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "No ingested sources yet." in response.text
