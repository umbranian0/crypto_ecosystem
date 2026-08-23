"""DASH-005-01: `GET /runs` (runs list) tests.

Mocks gateway-api the same way `tests/test_runs_detail.py` does --
`httpx.MockTransport` wired in via a `_patch_transport`-style monkeypatch of
`httpx.Client` itself (this router builds `httpx.Client(base_url=...)`
per-request rather than depending on an injectable client), preserving
`base_url` so relative outbound paths still resolve correctly.

The mock response bodies below are constructed directly from the documented
envelope shape in `services/gateway-api/README.md`'s Contract section
(`GET /runs`, GW-016 entry): `RunListResponse = {items: list[RunSummaryResponse],
limit: int, offset: int, total: int}`, `RunSummaryResponse = {id, dataset_id,
horizon, status, created_at, completed_at}` -- not guessed independently.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"
RUN_ID_1 = "11111111-1111-1111-1111-111111111111"
RUN_ID_2 = "22222222-2222-2222-2222-222222222222"

# Per services/gateway-api/README.md's Contract section, GET /runs (GW-016) entry:
# RunListResponse = {items: list[RunSummaryResponse], limit: int, offset: int, total: int}
# RunSummaryResponse = {id, dataset_id, horizon, status, created_at, completed_at}
RUNS_LIST_BODY = {
    "items": [
        {
            "id": RUN_ID_1,
            "dataset_id": "dataset-1",
            "horizon": 24,
            "status": "completed",
            "created_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T01:00:00Z",
        },
        {
            "id": RUN_ID_2,
            "dataset_id": "dataset-2",
            "horizon": 6,
            "status": "running",
            "created_at": "2026-08-01T00:00:00Z",
            "completed_at": None,
        },
    ],
    "limit": 50,
    "offset": 0,
    "total": 2,
}

EMPTY_RUNS_LIST_BODY = {"items": [], "limit": 50, "offset": 0, "total": 0}


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


def test_runs_list_success_with_multiple_runs(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        assert request.url.path == "/runs"
        return httpx.Response(200, json=RUNS_LIST_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200
    for run in RUNS_LIST_BODY["items"]:
        assert run["id"] in response.text
        assert run["status"] in response.text
        assert run["dataset_id"] in response.text
        assert str(run["horizon"]) in response.text
        assert run["created_at"][:10] in response.text
        assert f'href="/runs/{run["id"]}"' in response.text
    assert RUNS_LIST_BODY["items"][0]["completed_at"][:10] in response.text


def test_runs_list_success_with_zero_runs(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=EMPTY_RUNS_LIST_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200
    assert "No validation runs yet." in response.text


def test_runs_list_502_from_gateway_api(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "downstream service unavailable"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "downstream service unavailable" not in response.text


def test_runs_list_504_from_gateway_api(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, json={"detail": "downstream service timed out"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text
    assert "downstream service timed out" not in response.text


def test_runs_list_transport_connect_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "connection refused" not in response.text


def test_runs_list_transport_timeout(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text


def test_runs_list_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get("/runs", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_runs_list_template_has_no_banned_positioning_words() -> None:
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "runs_list.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in runs_list.html"
