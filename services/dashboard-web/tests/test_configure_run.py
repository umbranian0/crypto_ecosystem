"""AI-004-01: `parse_suggestion_lines` / `generate_run_suggestions` /
`build_configure_run_prompt` unit tests, plus `POST /assistant/configure-run`
route tests -- mirrors `tests/test_assistant.py`'s monkeypatch shape for
`app.routers.assistant.get_assist_client`.
"""

from __future__ import annotations

import pytest
from fastapi.testclient import TestClient
from naive_first_ai_assist.client import AssistClientError

from app.assistant.configure_run import (
    ConfigureRunResult,
    RunFieldSuggestion,
    generate_run_suggestions,
    parse_suggestion_lines,
)
from app.assistant.configure_run_prompt import build_configure_run_prompt
from app.assistant.fact_check import contains_overstated_certainty_claim
from app.dependencies.session import get_session_store
from app.main import app
from app.routers import assistant as assistant_router

RAW_KEY_A = "super-secret-raw-api-key-tenant-a"


@pytest.fixture(autouse=True)
def _clear_sessions_and_overrides():
    yield
    app.dependency_overrides.clear()
    get_session_store()._sessions.clear()


def _login(client: TestClient, raw_key: str) -> None:
    session_store = get_session_store()
    session_id = session_store.create(raw_key)
    client.cookies.set("session_id", session_id)


class _FakeAssistClient:
    def __init__(self, response_text: str):
        self._response_text = response_text
        self.calls: list[str] = []

    def generate(self, prompt: str) -> str:
        self.calls.append(prompt)
        return self._response_text


class _RaisingAssistClient:
    def __init__(self):
        self.calls = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        raise AssistClientError("boom")


# -- parse_suggestion_lines -------------------------------------------------


def test_parse_suggestion_lines_well_formed_input():
    text = "horizon: 24\npurge_gap_hours: 6\nlabel: my run"
    suggestions = parse_suggestion_lines(text)

    assert suggestions == [
        RunFieldSuggestion(
            field="horizon", value="24", explanation="Suggested value based on your answer, please confirm."
        ),
        RunFieldSuggestion(
            field="purge_gap_hours",
            value="6",
            explanation="Suggested value based on your answer, please confirm.",
        ),
        RunFieldSuggestion(
            field="label",
            value="my run",
            explanation="Suggested value based on your answer, please confirm.",
        ),
    ]


def test_parse_suggestion_lines_drops_unexpected_field_name():
    text = "horizon: 24\ndataset_id: dataset-1\ndataset_reference_url: http://example.com"
    suggestions = parse_suggestion_lines(text)

    fields = [s.field for s in suggestions]
    assert fields == ["horizon"]
    assert "dataset_id" not in fields
    assert not any(f.startswith("dataset_reference") for f in fields)


def test_parse_suggestion_lines_drops_malformed_line():
    text = "horizon: 24\nthis is not a valid line\npurge_gap_hours:"
    suggestions = parse_suggestion_lines(text)

    assert [s.field for s in suggestions] == ["horizon"]


def test_parse_suggestion_lines_empty_input():
    assert parse_suggestion_lines("") == []


# -- contains_overstated_certainty_claim ------------------------------------


def test_contains_overstated_certainty_claim_flags_optimal_best_correct():
    assert contains_overstated_certainty_claim("horizon: 24 is optimal") == "optimal"
    assert contains_overstated_certainty_claim("the best purge gap is 6") == "best"
    assert contains_overstated_certainty_claim("that is the correct value") == "correct"


def test_contains_overstated_certainty_claim_none_when_absent():
    assert contains_overstated_certainty_claim("horizon: 24") is None


# -- generate_run_suggestions ------------------------------------------------


def test_generate_run_suggestions_banned_term_never_reaches_caller():
    fake_client = _FakeAssistClient("horizon: 24 could produce a strong trading signal")

    result = generate_run_suggestions("I want to validate BTC returns", fake_client)

    assert result.degraded is True
    assert result.suggestions == []
    assert len(fake_client.calls) == 2


def test_generate_run_suggestions_overstated_certainty_never_reaches_caller():
    fake_client = _FakeAssistClient("horizon: 24 is the optimal choice")

    result = generate_run_suggestions("I want to validate BTC returns", fake_client)

    assert result.degraded is True
    assert result.suggestions == []
    assert len(fake_client.calls) == 2


def test_generate_run_suggestions_client_none_returns_degraded_no_exception():
    result = generate_run_suggestions("I want to validate BTC returns", None)

    assert result == ConfigureRunResult(suggestions=[], degraded=True)


def test_generate_run_suggestions_model_error_degrades_gracefully():
    raising_client = _RaisingAssistClient()

    result = generate_run_suggestions("I want to validate BTC returns", raising_client)

    assert result.degraded is True
    assert raising_client.calls == 2


def test_generate_run_suggestions_success_path():
    fake_client = _FakeAssistClient("horizon: 24\npurge_gap_hours: 6")

    result = generate_run_suggestions("I want to validate BTC returns", fake_client)

    assert result.degraded is False
    assert [s.field for s in result.suggestions] == ["horizon", "purge_gap_hours"]


# -- build_configure_run_prompt ---------------------------------------------


def test_configure_run_prompt_forbids_disabling_purge_gap_and_omitting_naive_baselines():
    prompt = build_configure_run_prompt("I want to validate BTC returns")

    lowered = prompt.lower()
    assert "never suggest disabling, omitting, or shortening the purge gap" in lowered
    assert "never suggest omitting the naive baselines" in lowered


# -- POST /assistant/configure-run route -------------------------------------


def test_configure_run_route_returns_200_when_model_call_fails(monkeypatch):
    raising_client = _RaisingAssistClient()
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: raising_client)

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.post(
        "/assistant/configure-run", data={"answer": "I want to validate BTC returns"}
    )

    assert response.status_code == 200
    assert "unavailable" in response.text.lower()


def test_configure_run_route_renders_suggestions_with_confirm_wording(monkeypatch):
    fake_client = _FakeAssistClient("horizon: 24\npurge_gap_hours: 6")
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: fake_client)

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.post(
        "/assistant/configure-run", data={"answer": "I want to validate BTC returns"}
    )

    assert response.status_code == 200
    assert "horizon" in response.text
    assert "24" in response.text
    assert "suggested value based on your answer, please confirm" in response.text.lower()


def test_configure_run_route_never_constructs_run_request_or_calls_post_runs(monkeypatch):
    """Ticket Implementation acceptance criteria: `RunRequest(` never appears
    in this ticket's diff, and this route makes no downstream HTTP call."""
    import inspect

    from app.routers import assistant as assistant_module

    source = inspect.getsource(assistant_module)
    assert "RunRequest(" not in source

    fake_client = _FakeAssistClient("horizon: 24")
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: fake_client)

    def _fail_if_httpx_client_used(*args, **kwargs):
        raise AssertionError("configure-run route must not call downstream gateway-api")

    monkeypatch.setattr("httpx.Client", _fail_if_httpx_client_used)

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.post(
        "/assistant/configure-run", data={"answer": "I want to validate BTC returns"}
    )

    assert response.status_code == 200
