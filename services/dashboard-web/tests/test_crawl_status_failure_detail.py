"""ADMIN-003-02: `_crawl_status_panel.html` status-cell tests for
`entry.failure_detail`, sourced from `ingestion-service`'s `GET
/connectors/{source}/status` response (`ADMIN-003-01`'s field addition).

Reuses `tests/test_monitoring.py`/`tests/test_crawl_progress.py`'s
`httpx.Client`-monkeypatching convention (`httpx.MockTransport`) and
tenant-session-cookie login helper -- no new mocking approach, and no live
ingestion-service required.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "crawl-failure-detail-test-raw-api-key"

_FAILURE_DETAIL = (
    "binance_price_btcusdt_1h: ConnectionError while fetching or writing -- see service logs for detail"
)


@pytest.fixture(autouse=True)
def _clear_sessions():
    yield
    get_session_store()._sessions.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


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


def _empty_runs_response() -> httpx.Response:
    return httpx.Response(200, json={"items": [], "limit": 100, "offset": 0, "total": 0})


def _handler_for(status: str, failure_detail: str | None):
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
                    "status": status,
                    "timestamp": "2026-01-02T00:00:00",
                    "row_count": 24,
                    "rows_fetched_so_far": None,
                    "updated_at": None,
                    "failure_detail": failure_detail,
                },
            )
        if request.url.path == "/diagnostics/recent-errors":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/runs":
            return _empty_runs_response()
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    return handler


def _login(client: TestClient) -> None:
    session_id = get_session_store().create(RAW_KEY)
    client.cookies.set("session_id", session_id)


def test_crawl_status_panel_renders_failure_detail_for_failed_status(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler_for("failed", _FAILURE_DETAIL))

    client = TestClient(app)
    _login(client)

    page_response = client.get("/monitoring")
    fragment_response = client.get("/monitoring/crawl-status-fragment")

    assert page_response.status_code == 200
    assert fragment_response.status_code == 200
    assert _FAILURE_DETAIL in page_response.text
    assert _FAILURE_DETAIL in fragment_response.text
    assert 'class="failure-detail"' in page_response.text
    assert 'class="failure-detail"' in fragment_response.text


def test_crawl_status_panel_omits_failure_detail_for_non_failed_status(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler_for("completed", None))

    client = TestClient(app)
    _login(client)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "failure-detail" not in response.text
    assert ">None<" not in response.text


def test_crawl_status_panel_handles_failed_status_with_null_failure_detail(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler_for("failed", None))

    client = TestClient(app)
    _login(client)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "failure-detail" not in response.text
    assert ">None<" not in response.text
