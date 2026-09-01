"""INGEST-007: `/health` real DB connectivity check.

Mirrors validation-service's own `tests/test_health.py` (OPS-005-01
convention): the `app.dependency_overrides` fake-engine pattern, non-
tautological assertions on both status code and response body shape.

`ingestion-service` is installed editable (`uv pip install -e .`) into this
service's own `.venv` -- `app.main`/`app.dependencies.repositories` import
directly, no `sys.path` insert needed (unlike `tests/test_credential_crypto.py`,
which predates this ticket's `pyproject.toml`-based packaging of `src/app`).
"""

from __future__ import annotations

from fastapi.testclient import TestClient


def test_health_healthy_returns_ok(tmp_path, monkeypatch):
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("INGESTION_SERVICE_DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


class _FakeConnection:
    def __enter__(self):
        return self

    def __exit__(self, *args):
        return False

    def execute(self, *args, **kwargs):
        raise AssertionError("execute() should never be reached: connect() already raised")


class _FakeEngineThatFailsToConnect:
    def connect(self):
        raise RuntimeError("password authentication failed for user 'app' at host db:5432")


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
    assert "app" not in body["detail"]


def test_health_response_carries_x_correlation_id_header(tmp_path, monkeypatch):
    """OPS-006: even a request with no inbound X-Correlation-Id header gets
    one generated and echoed back on the response -- CorrelationIdMiddleware
    is registered and active on this service's app, not just
    validation-service's/gateway-api's.
    """
    db_path = str(tmp_path / "test.db")
    monkeypatch.setenv("INGESTION_SERVICE_DB_PATH", db_path)
    monkeypatch.delenv("DATABASE_URL", raising=False)
    from app.main import app

    client = TestClient(app)
    response = client.get("/health")

    assert response.status_code == 200
    assert response.headers["X-Correlation-Id"]
