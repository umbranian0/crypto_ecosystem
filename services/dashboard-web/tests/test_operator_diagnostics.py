"""SETUP-021: `GET /diagnostics/recent-errors` (dashboard-web).

Mirrors gateway-api's own `tests/test_diagnostics.py` shape, applied to this
service's `require_operator_session` gate (`DASH-113`) instead of gateway-
api's `get_authenticated_operator`.
"""

from __future__ import annotations

import logging

from fastapi.testclient import TestClient

from app.dependencies.diagnostics import recent_errors_handler
from app.dependencies.operator_session import get_operator_session_store
from app.main import app

RAW_TOKEN = "the-operator-token"


def test_unauthenticated_redirects_to_operator_login() -> None:
    client = TestClient(app)

    response = client.get("/diagnostics/recent-errors", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_authenticated_returns_warning_records_but_not_info() -> None:
    recent_errors_handler.clear()
    try:
        logger = logging.getLogger("app.test_operator_diagnostics")
        logger.warning("a diagnosable warning for SETUP-021")
        logger.info("an info line that must never appear")

        store = get_operator_session_store()
        session_id = store.create(RAW_TOKEN)

        client = TestClient(app)
        client.cookies.set("operator_session_id", session_id)

        response = client.get("/diagnostics/recent-errors")

        assert response.status_code == 200
        messages = [item["message"] for item in response.json()["items"]]
        assert "a diagnosable warning for SETUP-021" in messages
        assert "an info line that must never appear" not in messages
    finally:
        recent_errors_handler.clear()
