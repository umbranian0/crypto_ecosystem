"""GW-022: `app.routers.system` (`GET /system/health`).

Fakes each of the three downstream clients independently via
`httpx.MockTransport` (same pattern `test_operator_routing.py`/
`test_downstream_failures.py` already use) and the gateway's own DB engine
via a fake engine (`test_health.py`'s existing pattern), proving:
- No auth is required to reach this endpoint.
- All-healthy: all four keys report `"ok"`.
- One-degraded: a downstream `/health` returning `503` maps to `"degraded"`
  for that service only, all others unaffected.
- One-unreachable: a downstream transport failure (connection refused /
  timeout) maps to `"unreachable"` for that service only, and the aggregate
  call itself still returns `200` -- one bad downstream must not fail the
  whole endpoint.
"""

from __future__ import annotations

import httpx
from fastapi.testclient import TestClient

from app.dependencies.http_client import (
    get_ingestion_service_client,
    get_reporting_service_client,
    get_validation_service_client,
)
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


def _ok_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(200, json={"status": "ok"})


def _degraded_handler(request: httpx.Request) -> httpx.Response:
    return httpx.Response(503, json={"status": "unhealthy", "detail": "database unreachable"})


def _connect_error_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.ConnectError("connection refused", request=request)


def _timeout_handler(request: httpx.Request) -> httpx.Response:
    raise httpx.TimeoutException("timed out", request=request)


def _mock_client(handler) -> httpx.Client:
    return httpx.Client(
        transport=httpx.MockTransport(handler),
        base_url="http://internal-service.example",
    )


def _override_all(monkeypatch, validation_handler, reporting_handler, ingestion_handler):
    app.dependency_overrides[get_health_check_engine] = lambda: _HealthyFakeEngine()
    app.dependency_overrides[get_validation_service_client] = lambda: _mock_client(
        validation_handler
    )
    app.dependency_overrides[get_reporting_service_client] = lambda: _mock_client(
        reporting_handler
    )
    app.dependency_overrides[get_ingestion_service_client] = lambda: _mock_client(
        ingestion_handler
    )


def _clear_overrides():
    for dep in (
        get_health_check_engine,
        get_validation_service_client,
        get_reporting_service_client,
        get_ingestion_service_client,
    ):
        app.dependency_overrides.pop(dep, None)


def test_all_healthy_reports_ok_for_every_service(monkeypatch) -> None:
    _override_all(monkeypatch, _ok_handler, _ok_handler, _ok_handler)
    try:
        response = TestClient(app).get("/system/health")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    assert response.json() == {
        "gateway-api": "ok",
        "validation-service": "ok",
        "reporting-service": "ok",
        "ingestion-service": "ok",
    }


def test_one_downstream_503_maps_to_degraded_for_that_service_only(monkeypatch) -> None:
    _override_all(monkeypatch, _degraded_handler, _ok_handler, _ok_handler)
    try:
        response = TestClient(app).get("/system/health")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["validation-service"] == "degraded"
    assert body["reporting-service"] == "ok"
    assert body["ingestion-service"] == "ok"
    assert body["gateway-api"] == "ok"


def test_one_downstream_connect_error_maps_to_unreachable_and_does_not_fail_aggregate(
    monkeypatch,
) -> None:
    _override_all(monkeypatch, _ok_handler, _connect_error_handler, _ok_handler)
    try:
        response = TestClient(app).get("/system/health")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["reporting-service"] == "unreachable"
    assert body["validation-service"] == "ok"
    assert body["ingestion-service"] == "ok"
    assert body["gateway-api"] == "ok"


def test_one_downstream_timeout_maps_to_unreachable_and_does_not_fail_aggregate(
    monkeypatch,
) -> None:
    _override_all(monkeypatch, _ok_handler, _ok_handler, _timeout_handler)
    try:
        response = TestClient(app).get("/system/health")
    finally:
        _clear_overrides()

    assert response.status_code == 200
    body = response.json()
    assert body["ingestion-service"] == "unreachable"
    assert body["validation-service"] == "ok"
    assert body["reporting-service"] == "ok"
    assert body["gateway-api"] == "ok"


def test_no_auth_required(monkeypatch) -> None:
    _override_all(monkeypatch, _ok_handler, _ok_handler, _ok_handler)
    try:
        response = TestClient(app).get("/system/health")
    finally:
        _clear_overrides()

    assert response.status_code != 401
