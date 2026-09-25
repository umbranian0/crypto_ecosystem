"""ADMIN-001: `app.health_monitor` -- background health-transition webhook.

Calls `evaluate_and_notify`/`run_health_monitor` as plain async functions
directly (via `asyncio.run(...)`, this repo has no `pytest-asyncio`
dependency anywhere -- confirmed by repo-wide grep before writing this file,
per the ticket's Analysis testability finding), rather than through
`TestClient`/FastAPI routing -- neither function touches FastAPI routing.

The one exception is `test_lifespan_launches_and_cancels_health_monitor_task`,
which deliberately *does* use `with TestClient(app) as client:` (Starlette's
`TestClient.__enter__` is the only place that actually runs `lifespan`
startup/shutdown -- a bare `TestClient(app)` call, the idiom every other
existing test file in this suite uses, never triggers `lifespan` at all), to
prove `main.py`'s new `lifespan=` wiring itself, not just the polling
function in isolation.
"""

from __future__ import annotations

import asyncio
import logging
from datetime import datetime

import httpx
from fastapi.testclient import TestClient

import app.main as main_module
from app import health_monitor
from app.dependencies.repositories import get_health_check_engine
from app.main import app


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return None


class _HealthyFakeEngine:
    def connect(self):
        return _FakeConnection()


class _AlternatingEngine:
    """Fails `connect()` exactly once, then succeeds on every subsequent
    call -- used to drive a real `non-healthy` -> `healthy` transition
    across two `run_health_monitor` iterations without needing a real DB.
    """

    def __init__(self) -> None:
        self.calls = 0

    def connect(self):
        self.calls += 1
        if self.calls == 1:
            raise ConnectionError("simulated database outage")
        return _FakeConnection()


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"status": "ok"})


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://internal-service.example")


def _recording_post(calls):
    def fake_post(url, **kwargs):
        calls.append({"url": url, **kwargs})
        return httpx.Response(200)

    return fake_post


def _raising_post(exc):
    def fake_post(url, **kwargs):
        raise exc

    return fake_post


# ---------------------------------------------------------------------------
# evaluate_and_notify
# ---------------------------------------------------------------------------


def test_transition_healthy_to_non_healthy_fires_exactly_one_webhook(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(health_monitor.httpx, "post", _recording_post(calls))

    result = asyncio.run(
        health_monitor.evaluate_and_notify(
            "healthy",
            compute_status=lambda: "non-healthy",
            webhook_url="http://example.test/webhook",
        )
    )

    assert result == "non-healthy"
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "http://example.test/webhook"
    assert call["timeout"] == 5.0
    payload = call["json"]
    assert set(payload.keys()) == {"event", "previous_status", "current_status", "at"}
    assert payload["event"] == "health_transition"
    assert payload["previous_status"] == "healthy"
    assert payload["current_status"] == "non-healthy"
    datetime.fromisoformat(payload["at"])


def test_transition_non_healthy_to_healthy_fires_exactly_one_webhook(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(health_monitor.httpx, "post", _recording_post(calls))

    result = asyncio.run(
        health_monitor.evaluate_and_notify(
            "non-healthy",
            compute_status=lambda: "healthy",
            webhook_url="http://example.test/webhook",
        )
    )

    assert result == "healthy"
    assert len(calls) == 1
    call = calls[0]
    assert call["url"] == "http://example.test/webhook"
    payload = call["json"]
    assert payload["event"] == "health_transition"
    assert payload["previous_status"] == "non-healthy"
    assert payload["current_status"] == "healthy"
    datetime.fromisoformat(payload["at"])


def test_no_change_healthy_stays_healthy_fires_zero_webhooks(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(health_monitor.httpx, "post", _recording_post(calls))

    result = asyncio.run(
        health_monitor.evaluate_and_notify(
            "healthy",
            compute_status=lambda: "healthy",
            webhook_url="http://example.test/webhook",
        )
    )

    assert result == "healthy"
    assert calls == []


def test_no_change_non_healthy_stays_non_healthy_fires_zero_webhooks(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(health_monitor.httpx, "post", _recording_post(calls))

    result = asyncio.run(
        health_monitor.evaluate_and_notify(
            "non-healthy",
            compute_status=lambda: "non-healthy",
            webhook_url="http://example.test/webhook",
        )
    )

    assert result == "non-healthy"
    assert calls == []


def test_first_evaluation_ever_fires_zero_webhooks_regardless_of_status(monkeypatch) -> None:
    calls: list[dict] = []
    monkeypatch.setattr(health_monitor.httpx, "post", _recording_post(calls))

    result = asyncio.run(
        health_monitor.evaluate_and_notify(
            None,
            compute_status=lambda: "non-healthy",
            webhook_url="http://example.test/webhook",
        )
    )

    assert result == "non-healthy"
    assert calls == []


def test_failed_webhook_delivery_is_logged_and_does_not_raise(monkeypatch, caplog) -> None:
    monkeypatch.setattr(
        health_monitor.httpx,
        "post",
        _raising_post(httpx.ConnectError("connection refused")),
    )

    with caplog.at_level(logging.WARNING, logger="app.health_monitor"):
        result = asyncio.run(
            health_monitor.evaluate_and_notify(
                "healthy",
                compute_status=lambda: "non-healthy",
                webhook_url="http://example.test/webhook",
            )
        )

    assert result == "non-healthy"
    assert any(
        record.levelno == logging.WARNING and "health_transition" in record.getMessage()
        for record in caplog.records
    )


def test_run_health_monitor_survives_failed_webhook_delivery_across_iterations(
    monkeypatch, caplog
) -> None:
    """Companion to the direct `evaluate_and_notify` failure test above --
    drives the same failure mode through the real `run_health_monitor` loop
    (`subscriber.py`-style `max_iterations` test seam), with `asyncio.sleep`
    monkeypatched to a no-op, proving the loop survives a bad delivery and
    completes both iterations without raising.
    """
    monkeypatch.setenv("MONITORING_WEBHOOK_URL", "http://example.test/webhook")

    engine = _AlternatingEngine()
    monkeypatch.setattr(health_monitor, "get_health_check_engine", lambda: engine)
    monkeypatch.setattr(health_monitor, "get_validation_service_client", lambda: _mock_client(_ok_handler))
    monkeypatch.setattr(health_monitor, "get_reporting_service_client", lambda: _mock_client(_ok_handler))
    monkeypatch.setattr(health_monitor, "get_ingestion_service_client", lambda: _mock_client(_ok_handler))
    monkeypatch.setattr(
        health_monitor.httpx,
        "post",
        _raising_post(httpx.ConnectError("connection refused")),
    )

    async def fake_sleep(*_args, **_kwargs) -> None:
        return None

    monkeypatch.setattr(health_monitor.asyncio, "sleep", fake_sleep)

    with caplog.at_level(logging.WARNING, logger="app.health_monitor"):
        asyncio.run(health_monitor.run_health_monitor(max_iterations=2))

    # First iteration: engine.connect() fails -> "non-healthy", but
    # previous_status was None so no webhook is attempted. Second iteration:
    # engine.connect() succeeds -> "healthy", a genuine transition from
    # "non-healthy" -> "healthy" fires the (failing) webhook.
    assert engine.calls == 2
    assert any("health_transition" in record.getMessage() for record in caplog.records)


def test_webhook_url_unset_never_posts(monkeypatch, caplog) -> None:
    monkeypatch.delenv("MONITORING_WEBHOOK_URL", raising=False)
    calls: list[dict] = []
    monkeypatch.setattr(health_monitor.httpx, "post", _recording_post(calls))

    with caplog.at_level(logging.WARNING):
        result = asyncio.run(
            health_monitor.evaluate_and_notify(
                "healthy",
                compute_status=lambda: "non-healthy",
            )
        )

    assert result == "non-healthy"
    assert calls == []
    assert not any(record.levelno >= logging.WARNING for record in caplog.records)


# ---------------------------------------------------------------------------
# lifespan wiring (main.py) -- the one test in this file that deliberately
# uses the context-manager form of TestClient.
# ---------------------------------------------------------------------------


def test_lifespan_launches_and_cancels_health_monitor_task(monkeypatch) -> None:
    events: list[str] = []

    async def fake_run_health_monitor(**kwargs) -> None:
        events.append("started")
        try:
            await asyncio.sleep(3600)
        except asyncio.CancelledError:
            events.append("cancelled")
            raise

    monkeypatch.setattr(main_module, "run_health_monitor", fake_run_health_monitor)
    app.dependency_overrides[get_health_check_engine] = lambda: _HealthyFakeEngine()
    try:
        with TestClient(app) as client:
            response = client.get("/health")
            assert response.status_code == 200
    finally:
        app.dependency_overrides.pop(get_health_check_engine, None)

    assert "started" in events
    assert "cancelled" in events
