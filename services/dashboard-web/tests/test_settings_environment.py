"""SETUP-015: `GET /settings/environment` tests.

Operator-session setup mirrors `tests/test_settings_connectors.py`'s own
`get_operator_session_store()`/`operator_session_id` cookie convention -- a
tenant's own `session_id` cookie (DASH-002/003) is never read by this
route's gate, so a request carrying only that cookie must be redirected the
same way an unauthenticated request is.
"""

from __future__ import annotations

import pathlib

import pytest
from fastapi.testclient import TestClient

from app.dependencies.operator_session import get_operator_session_store
from app.main import app

OPERATOR_TOKEN = "super-secret-operator-token"

_SECRET_DATABASE_URL = "postgresql://naive_first:hunter2@db-host:5432/naive_first"
_SECRET_OPERATOR_TOKEN_VALUE = "op-tok-abc123-super-secret"


@pytest.fixture(autouse=True)
def _clear_operator_sessions():
    yield
    get_operator_session_store()._sessions.clear()


def _operator_client() -> TestClient:
    client = TestClient(app)
    session_id = get_operator_session_store().create(OPERATOR_TOKEN)
    client.cookies.set("operator_session_id", session_id)
    return client


def test_no_session_at_all_redirected_to_operator_login() -> None:
    client = TestClient(app)

    response = client.get("/settings/environment", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_tenants_own_session_cannot_reach_settings_environment() -> None:
    client = TestClient(app)
    client.cookies.set("session_id", "irrelevant-tenant-session-value")

    response = client.get("/settings/environment", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/operator-login"


def test_operator_session_renders_expected_non_secret_facts(monkeypatch) -> None:
    monkeypatch.setenv("GATEWAY_API_URL", "http://gateway-api:8000")
    client = _operator_client()

    response = client.get("/settings/environment")

    assert response.status_code == 200
    assert "http://gateway-api:8000" in response.text
    assert "gateway-api" in response.text
    assert "validation-service" in response.text
    assert "reporting-service" in response.text
    assert "ingestion-service" in response.text
    assert "dashboard-web" in response.text
    assert "DATABASE_URL" in response.text
    assert "OPERATOR_TOKEN" in response.text
    assert "read-only" in response.text.lower()
    assert "infra/.env" in response.text


def test_no_secret_env_var_value_ever_rendered_even_when_set(monkeypatch) -> None:
    """Proves no secret env var value leaks into the rendered HTML, even when
    a realistic `DATABASE_URL`/`OPERATOR_TOKEN` is present in the test's own
    environment (the exact leak this ticket exists to prevent).
    """
    monkeypatch.setenv("DATABASE_URL", _SECRET_DATABASE_URL)
    monkeypatch.setenv("OPERATOR_TOKEN", _SECRET_OPERATOR_TOKEN_VALUE)
    client = _operator_client()

    response = client.get("/settings/environment")

    assert response.status_code == 200
    assert _SECRET_DATABASE_URL not in response.text
    assert _SECRET_OPERATOR_TOKEN_VALUE not in response.text
    assert "hunter2" not in response.text


def test_settings_environment_module_never_reads_secret_env_vars() -> None:
    """Static/source-level test: no `os.environ`/`os.getenv` read of a secret
    env var name exists anywhere in this router module's source. The only
    permitted `os.environ`-style read in this file is transitively via the
    imported `get_gateway_api_url()` (`GATEWAY_API_URL`), which this module
    never calls `os.environ` for directly.
    """
    module_path = (
        pathlib.Path(__file__).parent.parent
        / "src"
        / "app"
        / "routers"
        / "settings_environment.py"
    )
    source = module_path.read_text(encoding="utf-8")
    _, _, remainder = source.partition('"""')
    _, _, code_after_docstring = remainder.partition('"""')

    assert "os.environ" not in code_after_docstring
    assert "os.getenv" not in code_after_docstring
    assert "import os" not in code_after_docstring


def test_no_post_put_delete_route_in_settings_environment_module() -> None:
    module_path = (
        pathlib.Path(__file__).parent.parent
        / "src"
        / "app"
        / "routers"
        / "settings_environment.py"
    )
    source = module_path.read_text(encoding="utf-8")
    _, _, remainder = source.partition('"""')
    _, _, code_after_docstring = remainder.partition('"""')

    assert "@router.post" not in code_after_docstring
    assert "@router.put" not in code_after_docstring
    assert "@router.delete" not in code_after_docstring


def test_settings_environment_template_has_no_banned_positioning_words() -> None:
    template_path = (
        pathlib.Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "settings_environment.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, (
            f"banned positioning word {banned!r} found in settings_environment.html"
        )
