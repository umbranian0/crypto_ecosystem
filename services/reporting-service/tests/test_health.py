"""RS-007: `/health` real DB connectivity check.

Mirrors validation-service's own `test_health.py` (OPS-005-01) shape exactly.
Unlike validation-service, this service is Postgres-only with no SQLite
fallback (backlog decision 4), so both the healthy and failure paths use
`app.dependency_overrides` on `get_health_check_engine` with a fake engine
rather than requiring a real Postgres connection for either case.
"""

from __future__ import annotations

from fastapi.testclient import TestClient


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        return None


class _FakeEngineThatConnects:
    def connect(self):
        return _FakeConnection()


class _FakeConnectionThatFailsToExecute:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        raise RuntimeError(
            "connection to server at \"db\" (10.0.0.5), port 5432 failed: "
            "password authentication failed for user 'naive_first_app'"
        )


class _FakeEngineThatFailsToExecute:
    def connect(self):
        return _FakeConnectionThatFailsToExecute()


class _FakeEngineThatFailsToConnect:
    def connect(self):
        raise RuntimeError("password authentication failed for user 'naive_first_app' at host db:5432")


def test_health_healthy_returns_ok():
    from app.dependencies.repositories import get_health_check_engine
    from app.main import app

    app.dependency_overrides[get_health_check_engine] = lambda: _FakeEngineThatConnects()
    try:
        client = TestClient(app)
        response = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_health_check_engine, None)

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_health_unhealthy_when_connect_raises():
    from app.dependencies.repositories import get_health_check_engine
    from app.main import app

    app.dependency_overrides[get_health_check_engine] = lambda: _FakeEngineThatFailsToConnect()
    try:
        client = TestClient(app)
        response = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_health_check_engine, None)

    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "unhealthy", "detail": "database unreachable"}
    assert "password" not in response.text
    assert "naive_first_app" not in body["detail"]


def test_health_unhealthy_when_execute_raises():
    from app.dependencies.repositories import get_health_check_engine
    from app.main import app

    app.dependency_overrides[get_health_check_engine] = lambda: _FakeEngineThatFailsToExecute()
    try:
        client = TestClient(app)
        response = client.get("/health")
    finally:
        app.dependency_overrides.pop(get_health_check_engine, None)

    assert response.status_code == 503
    body = response.json()
    assert body == {"status": "unhealthy", "detail": "database unreachable"}
    assert "password" not in response.text
    assert "naive_first_app" not in body["detail"]
