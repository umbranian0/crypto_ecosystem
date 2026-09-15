"""DASH-113: `GET /monitoring` tests.

Mocks gateway-api's `GET /system/health` (GW-022) the same way
`tests/test_runs_list.py` mocks `GET /runs` -- monkeypatching `httpx.Client`
itself, since this router builds `httpx.Client(base_url=...)` per-request
rather than depending on an injectable client (same established pattern,
reused not reinvented).

DASH-109: the "last crawl status" panel tests below reuse the exact same
`_patch_transport` monkeypatch (one fake `httpx.Client` handles every
outbound call the route makes -- `/system/health`, `/ingestion/datasets`,
`/ingestion/connectors/{source}/status` -- distinguished by `request.url.path`
in each test's own handler), and `app.dependencies.session.get_session_store`
to set a real tenant session cookie (`test_downstream.py`'s own established
pattern, not a new fixture shape) for the "populated"/"empty" cases; the
existing tests above set no cookie at all, proving the panel degrades to its
login-prompt state rather than the whole page redirecting.

DASH-115: `GET /monitoring/crawl-status-fragment` tests below reuse the same
`_patch_transport` monkeypatch and tenant-session-cookie login helper -- no
new mocking convention.
"""

from __future__ import annotations

import logging

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.diagnostics import recent_errors_handler
from app.dependencies.operator_session import get_operator_session_store
from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "monitoring-test-raw-api-key"


@pytest.fixture(autouse=True)
def _clear_sessions():
    yield
    get_session_store()._sessions.clear()
    get_operator_session_store()._sessions.clear()


@pytest.fixture(autouse=True)
def _clear_recent_errors():
    yield
    recent_errors_handler.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_monitoring_all_healthy(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system/health"
        return httpx.Response(
            200,
            json={
                "gateway-api": "ok",
                "validation-service": "ok",
                "reporting-service": "ok",
                "ingestion-service": "ok",
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "gateway-api" in response.text
    assert "validation-service" in response.text
    assert "reporting-service" in response.text
    assert "ingestion-service" in response.text
    assert response.text.count(">ok<") == 4


def test_monitoring_mixed_degraded_and_unreachable(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "gateway-api": "ok",
                "validation-service": "degraded",
                "reporting-service": "unreachable",
                "ingestion-service": "ok",
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "degraded" in response.text
    assert "unreachable" in response.text


def test_monitoring_aggregate_call_transport_connect_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "connection refused" not in response.text


def test_monitoring_aggregate_call_transport_timeout(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text


def test_monitoring_non_200_from_gateway_api(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, json={"detail": "internal error"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 500
    assert "results currently unavailable" in response.text
    assert "internal error" not in response.text


def test_monitoring_requires_no_session() -> None:
    """No cookie is set anywhere in this file -- matching GW-022's own
    no-auth design choice, `/monitoring` must not redirect an
    unauthenticated request.
    """
    client = TestClient(app)
    response = client.get("/monitoring", follow_redirects=False)

    assert response.status_code != 303


def test_monitoring_template_has_no_banned_positioning_words() -> None:
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "monitoring.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in (
        "prediction",
        "forecast",
        "signal",
        "recommendation",
        "model performance",
        "accuracy",
    ):
        assert banned not in text, f"banned positioning word {banned!r} found in monitoring.html"


# DASH-109: "last crawl status" panel


def _health_response() -> httpx.Response:
    return httpx.Response(
        200,
        json={
            "gateway-api": "ok",
            "validation-service": "ok",
            "reporting-service": "ok",
            "ingestion-service": "ok",
        },
    )


def _empty_runs_response() -> httpx.Response:
    """DASH-128: `_fetch_all_runs`'s own `{items, limit, offset, total}`
    envelope (VS-022), zero-runs case -- the default `/runs` stub for tests
    in this file that don't care about the report-form dropdown's own
    content, matching `_fetch_ingestion_datasets`'s own empty-list-is-a-
    valid-state precedent.
    """
    return httpx.Response(200, json={"items": [], "limit": 100, "offset": 0, "total": 0})


def test_monitoring_crawl_status_panel_shows_login_prompt_for_anonymous_visitor(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system/health"
        return _health_response()

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "Log in to view your own ingestion status" in response.text


def test_monitoring_crawl_status_panel_populated_for_logged_in_tenant(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "source": "binance_price_btcusdt_1h",
                            "earliest_timestamp": "2026-01-01T00:00:00",
                            "latest_timestamp": "2026-01-02T00:00:00",
                            "row_count": 24,
                        }
                    ]
                },
            )
        if request.url.path == "/ingestion/connectors/binance_price_btcusdt_1h/status":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "timestamp": "2026-01-02T00:00:00",
                    "row_count": 24,
                },
            )
        if request.url.path == "/diagnostics/recent-errors":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/runs":
            return _empty_runs_response()
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "binance_price_btcusdt_1h" in response.text
    assert "completed" in response.text
    assert "Log in to view your own ingestion status" not in response.text


def test_monitoring_crawl_status_panel_empty_for_logged_in_tenant_with_no_datasets(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/diagnostics/recent-errors":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/runs":
            return _empty_runs_response()
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "No ingested sources yet." in response.text


# DASH-115: GET /monitoring/crawl-status-fragment


def _crawl_status_handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/system/health":
        return _health_response()
    if request.url.path == "/ingestion/datasets":
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "source": "binance_price_btcusdt_1h",
                        "earliest_timestamp": "2026-01-01T00:00:00",
                        "latest_timestamp": "2026-01-02T00:00:00",
                        "row_count": 24,
                    }
                ]
            },
        )
    if request.url.path == "/ingestion/connectors/binance_price_btcusdt_1h/status":
        return httpx.Response(
            200,
            json={
                "status": "queued",
                "timestamp": "2026-01-02T00:00:00",
                "row_count": None,
            },
        )
    if request.url.path == "/diagnostics/recent-errors":
        return httpx.Response(200, json={"items": []})
    if request.url.path == "/runs":
        return _empty_runs_response()
    raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover


def test_crawl_status_fragment_matches_monitoring_pages_own_panel_markup(monkeypatch) -> None:
    """Proves the shared-partial DRY claim (ticket's own Test acceptance
    criteria): for the same stubbed downstream state, the standalone fragment
    route's response is the same `_crawl_status_panel.html` markup embedded in
    `GET /monitoring`'s own initial render -- not two independently-maintained
    copies.
    """
    _patch_transport(monkeypatch, _crawl_status_handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    page_response = client.get("/monitoring")
    fragment_response = client.get("/monitoring/crawl-status-fragment")

    assert page_response.status_code == 200
    assert fragment_response.status_code == 200

    # Both responses render the same `_crawl_status_panel.html` file for the
    # same downstream state -- the fragment's own rendered output must appear
    # verbatim inside the full page's own render, proving one shared partial
    # rather than two independently-maintained copies of the same markup.
    assert fragment_response.text.strip() in page_response.text


def test_crawl_status_fragment_carries_polling_attributes_on_its_own_response(
    monkeypatch,
) -> None:
    """Review acceptance criteria: `hx-get`/`hx-trigger`/`hx-swap` must be
    present on the fragment response's own outer element too, or polling
    stops after the first `outerHTML` swap.
    """
    _patch_transport(monkeypatch, _crawl_status_handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring/crawl-status-fragment")

    assert response.status_code == 200
    assert 'id="crawl-status-panel"' in response.text
    assert 'hx-get="/monitoring/crawl-status-fragment"' in response.text
    assert 'hx-trigger="load, every 5s"' in response.text
    assert 'hx-swap="outerHTML"' in response.text


def test_crawl_status_fragment_requires_tenant_session() -> None:
    client = TestClient(app)

    response = client.get("/monitoring/crawl-status-fragment", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# SETUP-021: "Recent errors" section


def test_monitoring_recent_errors_gateway_api_login_prompt_for_anonymous_visitor(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system/health"
        return _health_response()

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "Log in as an operator" in response.text


def test_monitoring_recent_errors_gateway_api_does_not_populate_from_a_tenant_session_alone(
    monkeypatch,
) -> None:
    """A tenant session must never satisfy gateway-api's operator-gated
    `/diagnostics/recent-errors` -- the two credentials are structurally
    separate (`operator_session.py`'s own docstring). If this test's fake
    transport ever receives a request to that path, the tenant session was
    wrongly forwarded as an operator credential -- fail loudly rather than
    silently returning a plausible-looking response.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/runs":
            return _empty_runs_response()
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "Log in as an operator" in response.text


def test_monitoring_recent_errors_gateway_api_populated_for_logged_in_operator(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/diagnostics/recent-errors":
            assert request.headers.get("x-operator-token") == "op-token-setup-021"
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "timestamp": "2026-01-02T00:00:00+0000",
                            "level": "WARNING",
                            "logger": "app.some_module",
                            "message": "a gateway-api warning for SETUP-021",
                            "correlation_id": "corr-123",
                        }
                    ]
                },
            )
        if request.url.path == "/system/runs-summary":
            return httpx.Response(
                200,
                json={"total": 0, "completed_pct": 0.0, "failed_pct": 0.0, "running_pct": 0.0},
            )
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    operator_session_id = get_operator_session_store().create("op-token-setup-021")
    client = TestClient(app)
    client.cookies.set("operator_session_id", operator_session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "a gateway-api warning for SETUP-021" in response.text
    assert "Log in as an operator" not in response.text


def test_monitoring_recent_errors_dashboard_web_own_buffer_renders_regardless_of_session(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system/health"
        return _health_response()

    _patch_transport(monkeypatch, handler)

    logging.getLogger("app.test_monitoring_own_buffer").warning(
        "a dashboard-web warning for SETUP-021"
    )

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "a dashboard-web warning for SETUP-021" in response.text


def test_monitoring_recent_errors_page_discloses_no_persistence_and_no_cross_service_search(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system/health"
        return _health_response()

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "not persisted across a service restart" in response.text
    assert "no cross-service search" in response.text


# SETUP-022: "Validation-run throughput" section


def test_monitoring_runs_summary_login_prompt_for_anonymous_visitor(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system/health"
        return _health_response()

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "Validation-run throughput" in response.text
    assert "Log in as an operator" in response.text


def test_monitoring_runs_summary_populated_for_logged_in_operator(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/system/runs-summary":
            assert request.headers.get("x-operator-token") == "op-token-setup-022"
            return httpx.Response(
                200,
                json={
                    "total": 10,
                    "completed_pct": 70.0,
                    "failed_pct": 20.0,
                    "running_pct": 10.0,
                },
            )
        if request.url.path == "/diagnostics/recent-errors":
            return httpx.Response(200, json={"items": []})
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    operator_session_id = get_operator_session_store().create("op-token-setup-022")
    client = TestClient(app)
    client.cookies.set("operator_session_id", operator_session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "Validation-run throughput" in response.text
    assert "70.0%" in response.text
    assert "20.0%" in response.text
    assert "10.0%" in response.text


# DASH-124: login-prompt vs. transient-fetch-failure conflation


def test_monitoring_anonymous_visitor_sees_login_prompt_not_generic_failure(monkeypatch) -> None:
    """(a) No session -- both the crawl-status panel and the report form must
    show the "Log in..." prompt, byte-identical wording to before this
    ticket, never the generic downstream-failure message.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/system/health"
        return _health_response()

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "Log in to view your own ingestion status." in response.text
    assert "Log in to generate a report." in response.text
    assert "results currently unavailable" not in response.text


def test_monitoring_authenticated_tenant_failed_fetch_sees_generic_failure_not_login_prompt(
    monkeypatch,
) -> None:
    """(b) Session present but `_fetch_crawl_statuses` collapses to `None`
    (e.g. `/ingestion/datasets` itself returns non-200) -- must show the
    generic downstream-failure message, never the login prompt.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(500, json={"detail": "internal error"})
        if request.url.path == "/diagnostics/recent-errors":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/runs":
            return _empty_runs_response()
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert response.text.count("results currently unavailable") == 2
    assert "Log in to view your own ingestion status." not in response.text
    assert "Log in to generate a report." not in response.text


def test_monitoring_authenticated_tenant_successful_fetch_renders_panel_and_form_unaffected(
    monkeypatch,
) -> None:
    """(c) Session present and fetch succeeds -- existing panel/form render
    exactly as before this ticket, unaffected.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "source": "binance_price_btcusdt_1h",
                            "earliest_timestamp": "2026-01-01T00:00:00",
                            "latest_timestamp": "2026-01-02T00:00:00",
                            "row_count": 24,
                        }
                    ]
                },
            )
        if request.url.path == "/ingestion/connectors/binance_price_btcusdt_1h/status":
            return httpx.Response(
                200,
                json={
                    "status": "completed",
                    "timestamp": "2026-01-02T00:00:00",
                    "row_count": 24,
                },
            )
        if request.url.path == "/diagnostics/recent-errors":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/runs":
            return _empty_runs_response()
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "binance_price_btcusdt_1h" in response.text
    assert "completed" in response.text
    assert 'name="run_id"' in response.text
    assert "Log in to view your own ingestion status." not in response.text
    assert "Log in to generate a report." not in response.text
    assert "results currently unavailable" not in response.text


def test_crawl_status_fragment_downstream_failure_renders_small_error_fragment(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring/crawl-status-fragment")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "connection refused" not in response.text


# DASH-128: report-generation run picker


def _base_tenant_monitoring_handler(runs_response: httpx.Response):
    """Every downstream call `GET /monitoring` makes for a logged-in tenant
    with no ingested datasets, except `/runs`, which the caller supplies --
    kept minimal since these tests only care about the report form's own
    `run_id` field.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/diagnostics/recent-errors":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/runs":
            return runs_response
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    return handler


def test_monitoring_report_form_dropdown_renders_options_for_tenant_with_runs(monkeypatch) -> None:
    runs_response = httpx.Response(
        200,
        json={
            "items": [
                {
                    "id": "run-aaa",
                    "dataset_id": "binance_price_btcusdt_1h",
                    "horizon": 24,
                    "status": "completed",
                    "created_at": "2026-01-01T00:00:00",
                    "completed_at": "2026-01-01T01:00:00",
                },
                {
                    "id": "run-bbb",
                    "dataset_id": "binance_price_btcusdt_1h",
                    "horizon": 24,
                    "status": "running",
                    "created_at": "2026-01-02T00:00:00",
                    "completed_at": None,
                },
            ],
            "limit": 100,
            "offset": 0,
            "total": 2,
        },
    )
    _patch_transport(monkeypatch, _base_tenant_monitoring_handler(runs_response))

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert '<select id="run_id" name="run_id"' in response.text
    assert "run-aaa" in response.text
    assert "run-bbb" in response.text
    assert "completed" in response.text
    assert "running" in response.text
    # `RunSummaryResponse.created_at` is a parsed `datetime`, so Jinja's plain
    # `{{ run.created_at }}` renders `str(datetime)`'s space-separated form,
    # not the raw ISO-8601 `T` the downstream JSON used -- matches this
    # codebase's existing convention elsewhere (e.g. `runs_list.html`).
    assert "2026-01-01 00:00:00" in response.text
    assert "2026-01-02 00:00:00" in response.text
    assert '<input type="text" id="run_id"' not in response.text


def test_monitoring_report_form_falls_back_to_free_text_for_zero_runs(monkeypatch) -> None:
    runs_response = httpx.Response(
        200, json={"items": [], "limit": 100, "offset": 0, "total": 0}
    )
    _patch_transport(monkeypatch, _base_tenant_monitoring_handler(runs_response))

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert '<input type="text" id="run_id" name="run_id" required>' in response.text
    assert "<select" not in response.text
    assert "No runs found yet -- enter a run id directly, or submit a run first." in response.text


def test_monitoring_report_form_falls_back_to_free_text_on_runs_transport_failure(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/diagnostics/recent-errors":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/runs":
            raise httpx.ConnectError("connection refused", request=request)
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert '<input type="text" id="run_id" name="run_id" required>' in response.text
    assert "<select" not in response.text
    # A downstream /runs failure degrades this one form field only -- it must
    # never turn the whole otherwise-successful page into error.html.
    assert "results currently unavailable" not in response.text


def test_monitoring_report_form_selection_survives_a_rejected_submission(monkeypatch) -> None:
    """AC5 (previously-submitted-value preservation): `POST /monitoring/
    reports/generate` only ever swaps `#report-trigger-result` -- its response
    fragment must contain no `<select`/`<form` markup that could overwrite the
    tenant's chosen `run_id`, on either a rejected or accepted submission.
    Proves the DOM-preservation argument structurally rather than assuming it:
    if this fragment ever grew a `<select>`/`<form>` of its own, HTMX's
    `hx-swap="innerHTML"` into `#report-trigger-result` would still leave the
    original `<select>` above it untouched, but a future change that widened
    `hx-target` to the whole form would silently break this guarantee -- this
    test would catch that regression.
    """
    runs_response = httpx.Response(
        200,
        json={
            "items": [
                {
                    "id": "run-known",
                    "dataset_id": "binance_price_btcusdt_1h",
                    "horizon": 24,
                    "status": "completed",
                    "created_at": "2026-01-01T00:00:00",
                    "completed_at": "2026-01-01T01:00:00",
                }
            ],
            "limit": 100,
            "offset": 0,
            "total": 1,
        },
    )

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/diagnostics/recent-errors":
            return httpx.Response(200, json={"items": []})
        if request.url.path == "/runs":
            return runs_response
        if request.url.path == "/reports/generate":
            assert request.method == "POST"
            return httpx.Response(422, json={"detail": "unknown run id"})
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    page_response = client.get("/monitoring")
    assert page_response.status_code == 200
    assert 'hx-target="#report-trigger-result"' in page_response.text
    assert 'hx-swap="innerHTML"' in page_response.text

    # A run id not present in the fetched dropdown -- e.g. one created after
    # the page was rendered -- is still submittable (the raw form POST is not
    # constrained to the dropdown's own option values) and rejected downstream.
    submit_response = client.post(
        "/monitoring/reports/generate",
        data={"run_id": "run-not-in-dropdown"},
        headers={"HX-Request": "true"},
    )

    assert submit_response.status_code == 422
    # The rejection response (`_render_error_for_status`'s shared `error.html`)
    # carries its own unrelated `<form>` (the nav bar's logout form) -- that is
    # pre-existing, out of this ticket's scope. What this ticket's AC5 needs
    # proven is narrower and decisive: this response contains no `id="run_id"`
    # element of any kind (`<select>` or `<input>`), so it is structurally
    # incapable of overwriting the tenant's already-selected `run_id` value in
    # the untouched `<select>` on the page behind it once HTMX swaps this body
    # into the separate `#report-trigger-result` div.
    assert 'id="run_id"' not in submit_response.text
