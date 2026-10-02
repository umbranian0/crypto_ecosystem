"""ONB-002: `GET`/`POST /demo-run` tests (MockTransport style of test_runs_submit.py)."""

from __future__ import annotations

import json
import re

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"
RUN_ID = "33333333-3333-3333-3333-333333333333"
SAMPLE = {"source": "binance_price_btcusdt_1h", "earliest_timestamp": "2024-01-01T00:00:00",
          "latest_timestamp": "2024-06-01T00:00:00", "row_count": 10}

EXPECTED_BODY = {
    "dataset_id": "demo-binance_price_btcusdt_1h-volume",
    "dataset_reference": {
        "source": "binance_price_btcusdt_1h",
        "field": "volume",
        "start": "2024-01-01T00:00:00",
        "end": "2024-03-01T00:00:00",
    },
    "horizon": 1,
    "purge_gap_hours": 24,
    "train_window": 500,
    "test_window": 100,
    "step": 100,
    "client_prediction_reference": None,
    "feature_references": None,
    "missing_timestamp_policy": None,
    "label": "Demo run: demo configuration -- not a recommended default for your own data",
}


def _login(client: TestClient) -> None:
    client.cookies.set("session_id", get_session_store().create(RAW_KEY))


@pytest.fixture(autouse=True)
def _clear():
    yield
    app.dependency_overrides.clear()
    get_session_store()._sessions.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real = httpx.Client

    def _fake(*, base_url="", **kwargs):
        return real(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake)


def _forbid(request: httpx.Request) -> httpx.Response:
    raise AssertionError("gateway-api must not be called")


def test_get_renders_disclosure_config_and_button(monkeypatch) -> None:
    _patch_transport(monkeypatch, _forbid)
    client = TestClient(app)
    _login(client)

    response = client.get("/demo-run")

    assert response.status_code == 200
    text = response.text
    assert "demo configuration -- not a recommended default for your own data" in text
    assert "hourly traded volume" in text
    assert "returns guardrail" in text
    for value in ("binance_price_btcusdt_1h", "volume", "2024-01-01T00:00:00",
                  "2024-03-01T00:00:00", "500", "100", "24"):
        assert value in text
    assert "Run demo validation" in text
    assert 'href="/demo-run"' in text


def test_positioning_wording_absent(monkeypatch) -> None:
    _patch_transport(monkeypatch, _forbid)
    client = TestClient(app)
    _login(client)
    text = client.get("/demo-run").text.lower()
    for word in ("predict", "forecast", "signal", "recommend", "green", "red"):
        # the mandated sentence contains "recommended"; strip it before checking
        stripped = text.replace("not a recommended default", "")
        assert not re.search(rf"\b{word}", stripped), word


def test_post_happy_path_submits_exact_body_and_redirects(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": [SAMPLE]})
        assert request.url.path == "/runs"
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        assert json.loads(request.read()) == EXPECTED_BODY
        return httpx.Response(201, json={"id": RUN_ID, "status": "running"})

    _patch_transport(monkeypatch, handler)
    client = TestClient(app)
    _login(client)

    response = client.post("/demo-run", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{RUN_ID}"
    assert RAW_KEY not in response.headers["location"]


def test_post_without_sample_data_shows_message_and_makes_no_run_call(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json={"items": []})

    _patch_transport(monkeypatch, handler)
    client = TestClient(app)
    _login(client)

    response = client.post("/demo-run", follow_redirects=False)

    assert response.status_code == 200
    assert "Sample data is not loaded for this tenant. Ask your operator to seed it." in response.text
    assert "Run demo validation" not in response.text


def test_post_transport_failure_renders_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": [SAMPLE]})
        raise httpx.ConnectError("boom")

    _patch_transport(monkeypatch, handler)
    client = TestClient(app)
    _login(client)

    response = client.post("/demo-run", follow_redirects=False)

    assert response.status_code == 502
    assert RAW_KEY not in response.text


def test_post_downstream_non_2xx_renders_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": [SAMPLE]})
        return httpx.Response(422, json={"detail": "nope"})

    _patch_transport(monkeypatch, handler)
    client = TestClient(app)
    _login(client)

    response = client.post("/demo-run", follow_redirects=False)

    assert response.status_code == 422
    assert "Unavailable" in response.text


def test_repeat_post_submits_twice_with_no_other_calls(monkeypatch) -> None:
    calls: list[tuple[str, str]] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append((request.method, request.url.path))
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": [SAMPLE]})
        return httpx.Response(201, json={"id": RUN_ID, "status": "running"})

    _patch_transport(monkeypatch, handler)
    client = TestClient(app)
    _login(client)

    client.post("/demo-run", follow_redirects=False)
    client.post("/demo-run", follow_redirects=False)

    assert calls == [("GET", "/ingestion/datasets"), ("POST", "/runs")] * 2


@pytest.mark.parametrize("method", ["get", "post"])
def test_unauthenticated_rejected_without_downstream_calls(monkeypatch, method) -> None:
    _patch_transport(monkeypatch, _forbid)
    client = TestClient(app)

    response = getattr(client, method)("/demo-run", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_run_new_form_has_no_prefilled_demo_values(monkeypatch) -> None:
    _patch_transport(
        monkeypatch, lambda r: httpx.Response(200, json={"items": []})
    )
    client = TestClient(app)
    _login(client)

    text = client.get("/runs/new").text

    assert "Demo run --" not in text
    assert not re.search(r'value="(500|24|2024-01-01T00:00:00)"', text)
