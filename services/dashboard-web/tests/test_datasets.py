"""DASH-111: `GET /datasets` (dataset browsing view) tests.

Mocks gateway-api the same way `tests/test_runs_submit.py`'s
`test_run_new_form_populates_source_dropdown_from_ingestion_datasets`/
`test_run_new_form_empty_dataset_history_shows_messaging` already do --
`httpx.MockTransport` wired in via a `_patch_transport`-style monkeypatch of
`httpx.Client` itself, since this router builds `httpx.Client(base_url=...)`
per-request rather than depending on an injectable client.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"

DATASETS_BODY = {
    "items": [
        {
            "source": "binance_btcusdt_1h",
            "earliest_timestamp": "2024-01-01T00:00:00Z",
            "latest_timestamp": "2026-01-01T00:00:00Z",
            "row_count": 1000,
        },
        {
            "source": "reddit_sentiment",
            "earliest_timestamp": "2025-01-01T00:00:00Z",
            "latest_timestamp": "2026-06-01T00:00:00Z",
            "row_count": 42,
        },
    ]
}

EMPTY_DATASETS_BODY = {"items": []}


def _login(client: TestClient) -> None:
    session_store = get_session_store()
    session_id = session_store.create(RAW_KEY)
    client.cookies.set("session_id", session_id)


@pytest.fixture(autouse=True)
def _clear_sessions_and_overrides():
    yield
    app.dependency_overrides.clear()
    get_session_store()._sessions.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_datasets_list_populated(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json=DATASETS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/datasets")

    assert response.status_code == 200
    for dataset in DATASETS_BODY["items"]:
        assert dataset["source"] in response.text
        assert str(dataset["row_count"]) in response.text
    assert "No ingested datasets yet" not in response.text
    assert (
        'href="/runs/new?dataset_reference_source=binance_btcusdt_1h"' in response.text
    )
    assert 'href="/monitoring"' in response.text


def test_datasets_list_empty(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json=EMPTY_DATASETS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/datasets")

    assert response.status_code == 200
    assert "No ingested datasets yet -- run a crawl first." in response.text


def test_datasets_list_transport_failure_degrades_to_empty_state(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/datasets")

    assert response.status_code == 200
    assert "No ingested datasets yet -- run a crawl first." in response.text


def test_datasets_list_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get("/datasets", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_run_new_form_prefills_source_from_query_param(monkeypatch) -> None:
    """DASH-111: the "Submit a run" link on `GET /datasets` pre-selects the
    "Stored dataset" mode's source via `?dataset_reference_source=<source>`.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json=DATASETS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new?dataset_reference_source=binance_btcusdt_1h")

    assert response.status_code == 200
    import re

    assert re.search(
        r'<option value="binance_btcusdt_1h"[^>]*\s+selected>', response.text
    )


def test_datasets_list_template_has_no_banned_positioning_words() -> None:
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "datasets.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in datasets.html"
