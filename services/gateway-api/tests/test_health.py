"""OPS-005-02: `/health`'s real DB connectivity check.

Overrides `HealthCheckEngineDep` via `app.dependency_overrides` with a fake
engine, per this service's existing dependency-override/fake pattern (see
`tests/test_auth.py`/`tests/test_downstream_failures.py`).
"""

from __future__ import annotations

from fastapi.testclient import TestClient

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


class _UnhealthyFakeEngine:
    def connect(self):
        # Genuinely raises -- proves the failure path is not tautological.
        raise ConnectionError("simulated database outage")


def test_health_returns_ok_when_db_reachable() -> None:
    app.dependency_overrides[get_health_check_engine] = lambda: _HealthyFakeEngine()
    try:
        client = TestClient(app)
        response = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_health_check_engine, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_returns_503_when_db_unreachable() -> None:
    app.dependency_overrides[get_health_check_engine] = lambda: _UnhealthyFakeEngine()
    try:
        client = TestClient(app)
        response = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_health_check_engine, None)

    assert response.status_code == 503
    assert response.json() == {"status": "unhealthy", "detail": "database unreachable"}
