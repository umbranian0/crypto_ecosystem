"""DASH-006: `GET /runs/new` / `POST /runs/new` tests.

Fakes gateway-api with `httpx.MockTransport`, same approach as
`tests/test_runs_detail.py` -- `app.routers.runs` builds
`httpx.Client(base_url=base_url)` per-request rather than depending on an
injectable client, so the mock is wired in by monkeypatching `httpx.Client`
itself.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"
RUN_ID = "22222222-2222-2222-2222-222222222222"

VALID_FORM = {
    "dataset_id": "dataset-1",
    "dataset_reference_path": "/data/btc.csv",
    "dataset_reference_inline": "",
    "horizon": "24",
    "purge_gap_hours": "6",
    "train_window": "100",
    "test_window": "10",
    "step": "10",
}


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


def test_run_new_form_renders_without_downstream_call(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("GET /runs/new must not call gateway-api")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")

    assert response.status_code == 200
    assert "dataset_id" in response.text
    assert "purge_gap_hours" in response.text


def test_run_new_form_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get("/runs/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_run_new_submit_success_redirects_to_run_detail(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/runs"
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        body = request.read()
        import json

        payload = json.loads(body)
        assert payload["dataset_reference"] == {"path": "/data/btc.csv"}
        assert payload["horizon"] == 24
        assert payload["purge_gap_hours"] == 6
        return httpx.Response(201, json={"id": RUN_ID, "status": "running"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{RUN_ID}"


def test_run_new_submit_inline_reference(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        payload = json.loads(request.read())
        assert payload["dataset_reference"] == {
            "inline": {"timestamps": ["2026-01-01T00:00:00Z"], "values": [1.0]}
        }
        return httpx.Response(201, json={"id": RUN_ID, "status": "running"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {**VALID_FORM, "dataset_reference_path": ""}
    form["dataset_reference_inline"] = (
        '{"timestamps": ["2026-01-01T00:00:00Z"], "values": [1.0]}'
    )

    response = client.post("/runs/new", data=form, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{RUN_ID}"


def test_run_new_submit_201_with_failed_status_still_redirects(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": RUN_ID, "status": "failed"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{RUN_ID}"


def test_run_new_submit_no_dataset_reference_redisplays_form(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a dataset_reference")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {**VALID_FORM, "dataset_reference_path": "", "dataset_reference_inline": ""}

    response = client.post("/runs/new", data=form)

    assert response.status_code == 422
    assert "dataset-1" in response.text
    assert "Provide either a local file path" in response.text


def test_run_new_submit_invalid_inline_json_redisplays_form(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called with invalid inline JSON")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {**VALID_FORM, "dataset_reference_path": "", "dataset_reference_inline": "{not json"}

    response = client.post("/runs/new", data=form)

    assert response.status_code == 422
    assert "Inline payload must be valid JSON" in response.text


def test_run_new_submit_invalid_horizon_redisplays_form(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called with an invalid horizon")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {**VALID_FORM, "horizon": "0"}

    response = client.post("/runs/new", data=form)

    assert response.status_code == 422
    assert "dataset-1" in response.text


def test_run_new_submit_422_from_gateway_api_redisplays_form(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "dataset not found"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM)

    assert response.status_code == 422
    assert "dataset not found" in response.text
    assert "dataset-1" in response.text


def test_run_new_submit_502_from_gateway_api_renders_error_html(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "downstream service unavailable"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM)

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "downstream service unavailable" not in response.text


def test_run_new_submit_transport_connect_error_renders_error_html(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM)

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "connection refused" not in response.text


def test_run_new_submit_transport_timeout_renders_error_html(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM)

    assert response.status_code == 504
    assert "results currently unavailable" in response.text


def test_run_new_submit_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.post("/runs/new", data=VALID_FORM, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"
