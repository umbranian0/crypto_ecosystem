"""Smoke tests for the ECON-001 scaffold: the FastAPI app constructs and
`GET /health` responds, matching NFE-001/VS-001's precedent of a real,
non-vacuous test baseline (avoids pytest exit code 5 on zero-collected
tests, which would falsify "passing baseline").
"""

from __future__ import annotations

from fastapi.testclient import TestClient

from app.main import app


def test_app_constructs() -> None:
    assert app.title == "economic-service"


def test_health_endpoint_returns_ok() -> None:
    client = TestClient(app)
    response = client.get("/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}
