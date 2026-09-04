"""DASH-110: `POST /monitoring/connectors/{source}/run` /
`POST /monitoring/reports/generate` trigger-action tests.

Reuses `tests/test_monitoring.py`'s `_patch_transport` httpx.Client
monkeypatch (this router builds `httpx.Client(base_url=...)` per-request,
same as every other route in this service) and `tests/test_runs_submit.py`'s
tenant-session-cookie login helper -- no new mocking convention.

DASH-114: extends `trigger_crawl`'s own tests with the optional `since`
first-crawl override -- same fixtures/helpers, no new mocking convention.

DASH-115: `INGEST-015` made `POST /ingestion/connectors/{source}/run`
asynchronous (`202 {source, status: "queued", since, queued_at}`, no
`row_count`) -- the stubbed downstream responses below are updated to that
real shape instead of the pre-`INGEST-015` synchronous one.

DASH-117: `_monitoring_page_response`, `test_monitoring_page_renders_trigger_forms_for_logged_in_tenant`
and the new `test_monitoring_page_*_restart_form_*` tests below prove the
crawl-status panel's per-row trigger form is gated to
`completed`/`failed`/`cancelled` rows only, and labeled with
checkpoint-continuation copy -- no trigger form of any kind renders for a
`queued`/`running` row this ticket.

DASH-116: `POST /monitoring/connectors/{source}/cancel` tests below reuse
this same `_patch_transport`/`_login` convention -- no new mocking approach.
The template-gating tests parameterize over all six status values
(`queued`/`running`/`cancelling`/`cancelled`/`completed`/`failed`) to prove
the stop and restart controls partition that vocabulary with no overlap, per
the ticket's own binding Review acceptance criterion.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "monitoring-triggers-test-raw-api-key"

_QUEUED_RESPONSE_BODY = {
    "source": "binance_price_btcusdt_1h",
    "status": "queued",
    "since": "2026-01-01T00:00:00",
    "queued_at": "2026-01-02T00:00:00",
}


@pytest.fixture(autouse=True)
def _clear_sessions():
    yield
    get_session_store()._sessions.clear()


def _login(client: TestClient) -> None:
    session_id = get_session_store().create(RAW_KEY)
    client.cookies.set("session_id", session_id)


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


# POST /monitoring/connectors/{source}/run


def test_trigger_crawl_success_shows_queued_status_and_since(monkeypatch) -> None:
    """DASH-115: `INGEST-015` made this call asynchronous -- the response no
    longer carries `row_count`/a finished status.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/connectors/binance_price_btcusdt_1h/run"
        assert request.method == "POST"
        return httpx.Response(202, json=_QUEUED_RESPONSE_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/binance_price_btcusdt_1h/run")

    assert response.status_code == 200
    assert "binance_price_btcusdt_1h" in response.text
    assert "queued" in response.text
    assert "2026-01-01T00:00:00" in response.text
    assert "None rows" not in response.text
    assert "row_count" not in response.text


def test_trigger_crawl_with_since_forwards_since_param(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.params.get("since") == "2020-01-01"
        return httpx.Response(
            202,
            json={
                "source": "binance_price_btcusdt_1h",
                "status": "queued",
                "since": "2020-01-01T00:00:00",
                "queued_at": "2026-01-02T00:00:00",
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post(
        "/monitoring/connectors/binance_price_btcusdt_1h/run", data={"since": "2020-01-01"}
    )

    assert response.status_code == 200


def test_trigger_crawl_without_since_omits_since_param(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "since" not in request.url.params
        return httpx.Response(202, json=_QUEUED_RESPONSE_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/binance_price_btcusdt_1h/run")

    assert response.status_code == 200


def test_trigger_crawl_with_blank_since_omits_since_param(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert "since" not in request.url.params
        return httpx.Response(202, json=_QUEUED_RESPONSE_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post(
        "/monitoring/connectors/binance_price_btcusdt_1h/run", data={"since": ""}
    )

    assert response.status_code == 200


def test_trigger_crawl_downstream_422_renders_shared_error_page(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(422, json={"detail": "since must not be in the future"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post(
        "/monitoring/connectors/binance_price_btcusdt_1h/run",
        data={"since": "2099-01-01"},
    )

    assert response.status_code == 422
    assert "results currently unavailable" in response.text
    assert "since must not be in the future" not in response.text


def test_trigger_crawl_non_202_renders_shared_error_page(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "unknown source"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/unknown_source/run")

    assert response.status_code == 404
    assert "results currently unavailable" in response.text
    assert "unknown source" not in response.text


def test_trigger_crawl_transport_connect_error_renders_shared_error_page(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/binance_price_btcusdt_1h/run")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text


def test_trigger_crawl_transport_timeout_renders_shared_error_page(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/binance_price_btcusdt_1h/run")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text


def test_trigger_crawl_requires_tenant_session() -> None:
    client = TestClient(app)

    response = client.post(
        "/monitoring/connectors/binance_price_btcusdt_1h/run", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# POST /monitoring/reports/generate


def test_trigger_report_generation_success_shows_id_and_status(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/reports/generate"
        assert request.method == "POST"
        return httpx.Response(201, json={"id": "report-1", "status": "pending"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post(
        "/monitoring/reports/generate", data={"run_id": "11111111-1111-1111-1111-111111111111"}
    )

    assert response.status_code == 200
    assert "report-1" in response.text
    assert "pending" in response.text


def test_trigger_report_generation_non_201_renders_shared_error_page(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "unknown run"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/reports/generate", data={"run_id": "does-not-exist"})

    assert response.status_code == 404
    assert "results currently unavailable" in response.text
    assert "unknown run" not in response.text


def test_trigger_report_generation_transport_connect_error_renders_shared_error_page(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post(
        "/monitoring/reports/generate", data={"run_id": "11111111-1111-1111-1111-111111111111"}
    )

    assert response.status_code == 502
    assert "results currently unavailable" in response.text


def test_trigger_report_generation_requires_tenant_session() -> None:
    client = TestClient(app)

    response = client.post(
        "/monitoring/reports/generate",
        data={"run_id": "11111111-1111-1111-1111-111111111111"},
        follow_redirects=False,
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def _monitoring_page_response(monkeypatch, client: TestClient, crawl_status: str):
    """DASH-117: builds the same stubbed `/monitoring` fetch chain,
    parameterized on the one source's crawl `status` -- reused by every
    restart/stop-form-gating test below instead of a near-identical inline
    handler per test (this file's own DRY-reuse convention).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return httpx.Response(
                200,
                json={
                    "gateway-api": "ok",
                    "validation-service": "ok",
                    "reporting-service": "ok",
                    "ingestion-service": "ok",
                },
            )
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
                200, json={"status": crawl_status, "timestamp": "2026-01-02T00:00:00", "row_count": 24}
            )
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    return client.get("/monitoring")


def test_monitoring_page_renders_trigger_forms_for_logged_in_tenant(monkeypatch) -> None:
    client = TestClient(app)
    _login(client)

    response = _monitoring_page_response(monkeypatch, client, "completed")

    assert response.status_code == 200
    assert 'hx-post="/monitoring/connectors/binance_price_btcusdt_1h/run"' in response.text
    assert 'hx-post="/monitoring/reports/generate"' in response.text
    assert "continues from" in response.text


@pytest.mark.parametrize("crawl_status", ["completed", "failed", "cancelled"])
def test_monitoring_page_shows_restart_form_for_stopped_statuses(monkeypatch, crawl_status) -> None:
    """DASH-117: the restart form/button is present for a row whose crawl has
    actually stopped (`completed`/`failed`/`cancelled`), and its label carries
    checkpoint-continuation language, not an unqualified "Restart"."""
    client = TestClient(app)
    _login(client)

    response = _monitoring_page_response(monkeypatch, client, crawl_status)

    assert response.status_code == 200
    assert 'hx-post="/monitoring/connectors/binance_price_btcusdt_1h/run"' in response.text
    assert "continues from" in response.text


@pytest.mark.parametrize("crawl_status", ["queued", "running"])
def test_monitoring_page_hides_restart_form_for_in_progress_statuses(monkeypatch, crawl_status) -> None:
    """DASH-117: no restart form renders for a `queued`/`running` row --
    `DASH-116`'s stop button is what those rows render instead."""
    client = TestClient(app)
    _login(client)

    response = _monitoring_page_response(monkeypatch, client, crawl_status)

    assert response.status_code == 200
    assert "hx-post=\"/monitoring/connectors/binance_price_btcusdt_1h/run\"" not in response.text


def test_monitoring_page_hides_trigger_forms_for_anonymous_visitor(monkeypatch) -> None:
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
    assert "hx-post" not in response.text


# POST /monitoring/connectors/{source}/cancel


_CANCELLING_RESPONSE_BODY = {
    "source": "binance_price_btcusdt_1h",
    "status": "cancelling",
}


def test_cancel_crawl_success_shows_cancelling_status(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/connectors/binance_price_btcusdt_1h/cancel"
        assert request.method == "POST"
        return httpx.Response(202, json=_CANCELLING_RESPONSE_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/binance_price_btcusdt_1h/cancel")

    assert response.status_code == 200
    assert "binance_price_btcusdt_1h" in response.text
    assert "cancelling" in response.text
    assert "stopped" not in response.text.lower()


def test_cancel_crawl_downstream_404_renders_shared_error_page(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "unknown source"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/unknown_source/cancel")

    assert response.status_code == 404
    assert "results currently unavailable" in response.text
    assert "unknown source" not in response.text


def test_cancel_crawl_downstream_409_renders_shared_error_page(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(409, json={"detail": "nothing in progress to cancel"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/binance_price_btcusdt_1h/cancel")

    assert response.status_code == 409
    assert "results currently unavailable" in response.text
    assert "nothing in progress to cancel" not in response.text


def test_cancel_crawl_transport_connect_error_renders_shared_error_page(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/binance_price_btcusdt_1h/cancel")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text


def test_cancel_crawl_transport_timeout_renders_shared_error_page(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/monitoring/connectors/binance_price_btcusdt_1h/cancel")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text


def test_cancel_crawl_requires_tenant_session() -> None:
    client = TestClient(app)

    response = client.post(
        "/monitoring/connectors/binance_price_btcusdt_1h/cancel", follow_redirects=False
    )

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# `_crawl_status_panel.html` stop/restart gating (DASH-116)


@pytest.mark.parametrize("crawl_status", ["queued", "running", "cancelling"])
def test_monitoring_page_shows_stop_button_for_in_progress_statuses(monkeypatch, crawl_status) -> None:
    client = TestClient(app)
    _login(client)

    response = _monitoring_page_response(monkeypatch, client, crawl_status)

    assert response.status_code == 200
    assert 'hx-post="/monitoring/connectors/binance_price_btcusdt_1h/cancel"' in response.text


@pytest.mark.parametrize("crawl_status", ["cancelled", "completed", "failed"])
def test_monitoring_page_hides_stop_button_for_stopped_statuses(monkeypatch, crawl_status) -> None:
    client = TestClient(app)
    _login(client)

    response = _monitoring_page_response(monkeypatch, client, crawl_status)

    assert response.status_code == 200
    assert 'hx-post="/monitoring/connectors/binance_price_btcusdt_1h/cancel"' not in response.text


def test_monitoring_page_disables_stop_button_while_cancelling(monkeypatch) -> None:
    client = TestClient(app)
    _login(client)

    response = _monitoring_page_response(monkeypatch, client, "cancelling")

    assert response.status_code == 200
    assert "Stopping" in response.text
    assert "<button type=\"submit\" disabled>Stopping" in response.text
    assert "Stop this crawl" not in response.text


@pytest.mark.parametrize("crawl_status", ["queued", "running"])
def test_monitoring_page_stop_button_not_disabled_while_queued_or_running(
    monkeypatch, crawl_status
) -> None:
    client = TestClient(app)
    _login(client)

    response = _monitoring_page_response(monkeypatch, client, crawl_status)

    assert response.status_code == 200
    assert "Stop this crawl" in response.text
    assert "disabled" not in response.text


@pytest.mark.parametrize(
    "crawl_status", ["queued", "running", "cancelling", "cancelled", "completed", "failed"]
)
def test_monitoring_page_never_shows_both_stop_and_restart_for_same_row(
    monkeypatch, crawl_status
) -> None:
    """DASH-116's Review acceptance criterion: the six-value status
    vocabulary must partition cleanly across the stop gate and DASH-117's
    restart gate -- checked for all six values, not just a couple."""
    client = TestClient(app)
    _login(client)

    response = _monitoring_page_response(monkeypatch, client, crawl_status)

    assert response.status_code == 200
    has_stop = 'hx-post="/monitoring/connectors/binance_price_btcusdt_1h/cancel"' in response.text
    has_restart = 'hx-post="/monitoring/connectors/binance_price_btcusdt_1h/run"' in response.text
    assert not (has_stop and has_restart)
    assert has_stop or has_restart
