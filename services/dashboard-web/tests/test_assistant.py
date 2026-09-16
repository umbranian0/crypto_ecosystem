"""AI-003: `GET /assistant` / `POST /assistant/ask` tests.

Mocks gateway-api the same way `tests/test_runs_detail.py`/`tests/test_datasets
.py` already do -- `httpx.MockTransport` wired in via a `_patch_transport`
monkeypatch of `httpx.Client` itself, since `app.assistant.retrieval` (via
`app.routers.assistant`) builds `httpx.Client(base_url=...)` per-request
rather than depending on an injectable client.

`app.routers.assistant.get_assist_client` is monkeypatched directly (it is
imported by name into that module's namespace) to substitute a fake
`AssistClient`, mirroring how every other route's tests already monkeypatch
module-level names rather than reaching into `libs/ai_assist` itself.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient
from naive_first_ai_assist.client import AssistClientError

from app.dependencies.session import get_session_store
from app.main import app
from app.routers import assistant as assistant_router

RAW_KEY_A = "super-secret-raw-api-key-tenant-a"
RAW_KEY_B = "super-secret-raw-api-key-tenant-b"

RUN_ID_A = "aaaaaaaa-aaaa-aaaa-aaaa-aaaaaaaaaaaa"
RUN_ID_B = "bbbbbbbb-bbbb-bbbb-bbbb-bbbbbbbbbbbb"


def _run_summary_body(run_id: str) -> dict:
    return {
        "id": run_id,
        "dataset_id": "dataset-1",
        "horizon": 24,
        "status": "completed",
        "created_at": "2026-08-01T00:00:00Z",
        "completed_at": "2026-08-01T01:00:00Z",
        "label": None,
    }


def _run_detail_body(run_id: str) -> dict:
    return {
        "id": run_id,
        "tenant_id": "irrelevant",
        "dataset_id": "dataset-1",
        "horizon": 24,
        "purge_gap_hours": 6,
        "split_config": {"train_window": 100, "test_window": 10, "step": 10},
        "status": "completed",
        "created_at": "2026-08-01T00:00:00Z",
        "completed_at": "2026-08-01T01:00:00Z",
        "failure_reason": None,
    }


def _split_body(split_index: int) -> dict:
    return {
        "split_index": split_index,
        "train_start": "2026-01-01T00:00:00Z",
        "train_end": "2026-01-10T00:00:00Z",
        "purge_start": "2026-01-10T00:00:00Z",
        "purge_end": "2026-01-10T06:00:00Z",
        "test_start": "2026-01-10T06:00:00Z",
        "test_end": "2026-01-11T00:00:00Z",
        "model_mae": 1.1,
        "model_rmse": 2.2,
        "model_smape": 3.3,
        "model_mase": 4.4,
        "model_da": 0.5,
        "model_f1": 0.6,
        "model_oos_r2": 0.1,
        "naive0_mae": 1.0,
        "naive0_rmse": 2.0,
        "naive0_smape": 3.0,
        "naive0_mase": 4.0,
        "naive0_da": 0.51,
        "naive0_f1": 0.61,
        "naive0_oos_r2": 0.12,
        "dm_statistic": -0.9,
        "dm_pvalue": 0.42,
        "dm_verdict": "no significant difference",
    }


def _login(client: TestClient, raw_key: str) -> None:
    session_store = get_session_store()
    session_id = session_store.create(raw_key)
    client.cookies.set("session_id", session_id)


@pytest.fixture(autouse=True)
def _clear_sessions_and_overrides():
    yield
    app.dependency_overrides.clear()
    get_session_store()._sessions.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


class _FakeAssistClient:
    def __init__(self, response_text: str = "The model was consistent with Naive0 on this split."):
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


def _handler_for_tenant(raw_key: str, run_id: str):
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {raw_key}"
        if request.url.path == "/runs":
            return httpx.Response(200, json={"items": [_run_summary_body(run_id)]})
        if request.url.path == f"/runs/{run_id}":
            return httpx.Response(200, json=_run_detail_body(run_id))
        if request.url.path == f"/runs/{run_id}/splits":
            return httpx.Response(200, json=[_split_body(0)])
        raise AssertionError(f"unexpected path {request.url.path}")

    return handler


def test_assistant_form_renders_positioning_copy_and_requires_session(monkeypatch) -> None:
    client = TestClient(app)

    unauthenticated_response = client.get("/assistant", follow_redirects=False)
    assert unauthenticated_response.status_code == 303
    assert unauthenticated_response.headers["location"] == "/login"

    _login(client, RAW_KEY_A)
    response = client.get("/assistant")

    assert response.status_code == 200
    assert "does not predict prices or markets" in response.text


def test_citation_footer_names_the_real_mocked_run_and_split(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler_for_tenant(RAW_KEY_A, RUN_ID_A))
    fake_client = _FakeAssistClient()
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: fake_client)

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.post("/assistant/ask", data={"question": "How did my most recent run do?"})

    assert response.status_code == 200
    assert f"run {RUN_ID_A}" in response.text
    assert "split 0" in response.text
    assert len(fake_client.calls) == 1


def test_cross_tenant_leak_guard_answers_only_reflect_the_calling_tenants_own_data(
    monkeypatch,
) -> None:
    """VS-024 precedent: two distinct tenant sessions, distinct mocked
    gateway-api responses per tenant, asserted by real id in both directions
    -- not merely "a response came back".
    """

    def handler(request: httpx.Request) -> httpx.Response:
        auth = request.headers["authorization"]
        if auth == f"Bearer {RAW_KEY_A}":
            return _handler_for_tenant(RAW_KEY_A, RUN_ID_A)(request)
        if auth == f"Bearer {RAW_KEY_B}":
            return _handler_for_tenant(RAW_KEY_B, RUN_ID_B)(request)
        raise AssertionError(f"unexpected authorization header {auth!r}")

    _patch_transport(monkeypatch, handler)
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: _FakeAssistClient())

    client_a = TestClient(app)
    _login(client_a, RAW_KEY_A)
    response_a = client_a.post("/assistant/ask", data={"question": "How did my most recent run do?"})

    client_b = TestClient(app)
    _login(client_b, RAW_KEY_B)
    response_b = client_b.post("/assistant/ask", data={"question": "How did my most recent run do?"})

    assert response_a.status_code == 200
    assert response_b.status_code == 200
    assert f"run {RUN_ID_A}" in response_a.text
    assert f"run {RUN_ID_B}" not in response_a.text
    assert f"run {RUN_ID_B}" in response_b.text
    assert f"run {RUN_ID_A}" not in response_b.text


def test_banned_term_in_generated_answer_degrades_to_unavailable(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler_for_tenant(RAW_KEY_A, RUN_ID_A))
    fake_client = _FakeAssistClient(response_text="This run could produce a strong trading signal.")
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: fake_client)

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.post("/assistant/ask", data={"question": "How did my most recent run do?"})

    assert response.status_code == 200
    assert "currently unavailable" in response.text
    assert "signal" not in response.text
    # Regenerate-once-then-fallback: both attempts are rejected, so exactly
    # `_MAX_ATTEMPTS` calls were made, not an open-ended retry loop.
    assert len(fake_client.calls) == 2


def test_assistant_html_static_copy_contains_no_banned_term() -> None:
    from app.assistant.fact_check import BANNED_TERMS

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.get("/assistant")

    lowered = response.text.lower()
    for term in BANNED_TERMS:
        assert term not in lowered, f"banned term {term!r} present in assistant.html's static copy"


def test_out_of_scope_question_is_refused_without_any_model_call(monkeypatch) -> None:
    fake_client = _FakeAssistClient()
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: fake_client)

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("retrieval must not be reachable for an out-of-scope question test")

    # Retrieval still runs (fixed call pattern, independent of question
    # content) -- so wire a normal tenant handler, not an assertion failure.
    _patch_transport(monkeypatch, _handler_for_tenant(RAW_KEY_A, RUN_ID_A))

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.post("/assistant/ask", data={"question": "will Bitcoin go up next week"})

    assert response.status_code == 200
    assert "does not predict prices or markets" in response.text
    assert fake_client.calls == []


def test_model_call_error_degrades_gracefully_no_exception_no_hang(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler_for_tenant(RAW_KEY_A, RUN_ID_A))
    raising_client = _RaisingAssistClient()
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: raising_client)

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.post("/assistant/ask", data={"question": "How did my most recent run do?"})

    assert response.status_code == 200
    assert "currently unavailable" in response.text
    assert raising_client.calls == 2


def test_unconfigured_assist_client_degrades_gracefully(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler_for_tenant(RAW_KEY_A, RUN_ID_A))
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: None)

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.post("/assistant/ask", data={"question": "How did my most recent run do?"})

    assert response.status_code == 200
    assert "currently unavailable" in response.text


def test_zero_runs_tenant_makes_no_retrieval_call_beyond_get_runs_and_states_no_data(
    monkeypatch,
) -> None:
    calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        calls.append(request.url.path)
        if request.url.path == "/runs":
            return httpx.Response(200, json={"items": []})
        raise AssertionError(f"unexpected path {request.url.path} for a zero-runs tenant")

    _patch_transport(monkeypatch, handler)
    fake_client = _FakeAssistClient()
    monkeypatch.setattr(assistant_router, "get_assist_client", lambda: fake_client)

    client = TestClient(app)
    _login(client, RAW_KEY_A)

    response = client.post("/assistant/ask", data={"question": "How did my most recent run do?"})

    assert response.status_code == 200
    assert "no recorded validation runs yet" in response.text
    assert calls == ["/runs"]
    assert fake_client.calls == []
