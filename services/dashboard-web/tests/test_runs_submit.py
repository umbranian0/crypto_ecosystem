"""DASH-006: `GET /runs/new` / `POST /runs/new` tests.

Fakes gateway-api with `httpx.MockTransport`, same approach as
`tests/test_runs_detail.py` -- `app.routers.runs` builds
`httpx.Client(base_url=base_url)` per-request rather than depending on an
injectable client, so the mock is wired in by monkeypatching `httpx.Client`
itself.
"""

from __future__ import annotations

import re

import httpx
import pytest
from fastapi.testclient import TestClient
from naive_first_common.contracts import DatasetSummaryResponse

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"
RUN_ID = "22222222-2222-2222-2222-222222222222"

VALID_FORM = {
    "dataset_id": "dataset-1",
    "dataset_reference_path": "/data/btc.csv",
    "dataset_reference_inline": "",
    "horizon": "24",
    "purge_gap_hours": "6",
    "train_window": "100",
    "test_window": "10",
    "step": "10",
}


def _login(client: TestClient) -> None:
    session_store = get_session_store()
    session_id = session_store.create(RAW_KEY)
    client.cookies.set("session_id", session_id)


@pytest.fixture(autouse=True)
def _clear_sessions_and_overrides():
    yield
    app.dependency_overrides.clear()
    get_session_store()._sessions.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_run_new_form_renders_and_fetches_ingestion_datasets(monkeypatch) -> None:
    """DASH-108: `GET /runs/new` now also calls `GET /ingestion/datasets`
    (GW-020) to populate the "Stored dataset" mode's source dropdown -- see
    `app.routers.runs.run_new_form`'s own docstring. The pre-DASH-108 form
    fields/behavior are otherwise unchanged.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json={"items": []})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")

    assert response.status_code == 200
    assert "dataset_id" in response.text
    assert "purge_gap_hours" in response.text


def test_run_new_form_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get("/runs/new", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_run_new_submit_success_redirects_to_run_detail(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/runs"
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        body = request.read()
        import json

        payload = json.loads(body)
        assert payload["dataset_reference"] == {"path": "/data/btc.csv"}
        assert payload["horizon"] == 24
        assert payload["purge_gap_hours"] == 6
        return httpx.Response(201, json={"id": RUN_ID, "status": "running"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{RUN_ID}"


def test_run_new_submit_inline_reference(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        payload = json.loads(request.read())
        assert payload["dataset_reference"] == {
            "inline": {"timestamps": ["2026-01-01T00:00:00Z"], "values": [1.0]}
        }
        return httpx.Response(201, json={"id": RUN_ID, "status": "running"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {**VALID_FORM, "dataset_reference_path": ""}
    form["dataset_reference_inline"] = (
        '{"timestamps": ["2026-01-01T00:00:00Z"], "values": [1.0]}'
    )

    response = client.post("/runs/new", data=form, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{RUN_ID}"


def test_run_new_submit_201_with_failed_status_still_redirects(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(201, json={"id": RUN_ID, "status": "failed"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{RUN_ID}"


# DASH-120: a `POST /runs/new` request rejected for any reason (missing
# reference, invalid inline JSON, invalid horizon, or gateway-api's own 422 --
# e.g. RSS-004's too-many-splits guardrail, the exact real-world case that
# surfaced this bug) must re-fetch and redisplay the tenant's stored datasets,
# not silently collapse the "Stored dataset" dropdown to the misleading
# "No ingested datasets yet" empty state. Each handler below now answers
# `GET /ingestion/datasets` (the only downstream call some of these paths make
# at all) so the fix's re-fetch is actually exercised, not merely untested.

_ONE_STORED_DATASET_RESPONSE = httpx.Response(
    200,
    json={
        "items": [
            {
                "source": "binance_btcusdt_1h",
                "earliest_timestamp": "2024-01-01T00:00:00Z",
                "latest_timestamp": "2026-01-01T00:00:00Z",
                "row_count": 1000,
            },
        ]
    },
)


def test_run_new_submit_no_dataset_reference_redisplays_form(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return _ONE_STORED_DATASET_RESPONSE

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {**VALID_FORM, "dataset_reference_path": "", "dataset_reference_inline": ""}

    response = client.post("/runs/new", data=form)

    assert response.status_code == 422
    assert "dataset-1" in response.text
    assert "Provide either a local file path" in response.text
    # DASH-120: the stored-dataset dropdown must survive this rejection.
    assert "binance_btcusdt_1h" in response.text
    assert "No ingested datasets yet" not in response.text


def test_run_new_submit_invalid_inline_json_redisplays_form(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return _ONE_STORED_DATASET_RESPONSE

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {**VALID_FORM, "dataset_reference_path": "", "dataset_reference_inline": "{not json"}

    response = client.post("/runs/new", data=form)

    assert response.status_code == 422
    assert "Inline payload must be valid JSON" in response.text
    assert "binance_btcusdt_1h" in response.text
    assert "No ingested datasets yet" not in response.text


def test_run_new_submit_invalid_horizon_redisplays_form(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return _ONE_STORED_DATASET_RESPONSE

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {**VALID_FORM, "horizon": "0"}

    response = client.post("/runs/new", data=form)

    assert response.status_code == 422
    assert "dataset-1" in response.text
    assert "binance_btcusdt_1h" in response.text
    assert "No ingested datasets yet" not in response.text


def test_run_new_submit_invalid_horizon_shows_human_readable_error(monkeypatch) -> None:
    """QA-found (Sprint 31 UAT sweep, unfiled ticket as of this test): a
    client-side Pydantic `RunRequest(...)` construction failure (e.g.
    `horizon=0`, `services/dashboard-web/src/app/routers/runs.py`'s
    `run_new_submit`, the `except (ValueError, ValidationError) as exc`
    branch) currently renders `str(exc)` verbatim into the `.error` paragraph
    -- e.g. "1 validation error for RunRequest\\nhorizon\\n  Input should be
    greater than or equal to 1 [type=greater_than_equal, ...]\\n    For
    further information visit https://errors.pydantic.dev/...". This leaks
    the internal Pydantic model's class name and a pydantic.dev doc link to
    the end user and is inconsistent with this same route's other two
    hand-written, human-readable error strings
    (`_MISSING_DATASET_REFERENCE_ERROR`/`_INVALID_INLINE_JSON_ERROR`). This
    test currently fails, documenting the gap for the Tech Lead to route to
    a dev agent; QA does not patch this production-behavior fix itself.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return _ONE_STORED_DATASET_RESPONSE

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {**VALID_FORM, "horizon": "0"}

    response = client.post("/runs/new", data=form)

    assert response.status_code == 422
    assert "RunRequest" not in response.text
    assert "pydantic.dev" not in response.text
    assert "type=greater_than_equal" not in response.text


def test_run_new_submit_422_from_gateway_api_redisplays_form(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ingestion/datasets":
            return _ONE_STORED_DATASET_RESPONSE
        return httpx.Response(422, json={"detail": "dataset not found"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM)

    assert response.status_code == 422
    assert "dataset not found" in response.text
    assert "dataset-1" in response.text
    assert "binance_btcusdt_1h" in response.text
    assert "No ingested datasets yet" not in response.text


def test_run_new_submit_split_cap_422_preserves_stored_dataset_selection(monkeypatch) -> None:
    """DASH-120 regression: the exact real-world scenario that surfaced this
    bug -- a stored-dataset run submission rejected by RSS-004's too-many-
    splits guardrail must redisplay with the dataset dropdown intact and the
    submitted values preserved, so the live estimate can immediately guide a
    correction instead of forcing the user to start over from an empty form.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/ingestion/datasets":
            return _ONE_STORED_DATASET_RESPONSE
        assert request.url.path == "/runs"
        return httpx.Response(
            422,
            json={
                "detail": (
                    "This request would compute 39550 splits, exceeding the "
                    "maximum of 500 splits allowed per run."
                )
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {
        **VALID_FORM,
        "dataset_reference_path": "",
        "dataset_reference_inline": "",
        "dataset_reference_source": "binance_btcusdt_1h",
        "train_window": "72",
        "test_window": "2",
        "step": "2",
    }

    response = client.post("/runs/new", data=form)

    assert response.status_code == 422
    assert "exceeding the maximum of 500 splits" in response.text
    # The dropdown must be repopulated AND the user's prior selection restored
    # -- not just present, but re-selected, so the live estimate has something
    # to compute against without the user reselecting it.
    assert "binance_btcusdt_1h" in response.text
    assert "No ingested datasets yet" not in response.text
    assert 'value="binance_btcusdt_1h" selected' in response.text or "selected>" in response.text


def test_run_new_submit_502_from_gateway_api_renders_error_html(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "downstream service unavailable"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM)

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "downstream service unavailable" not in response.text


def test_run_new_submit_transport_connect_error_renders_error_html(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM)

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "connection refused" not in response.text


def test_run_new_submit_transport_timeout_renders_error_html(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.post("/runs/new", data=VALID_FORM)

    assert response.status_code == 504
    assert "results currently unavailable" in response.text


def test_run_new_submit_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.post("/runs/new", data=VALID_FORM, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


# DASH-108: "Stored dataset" third mode.


def test_run_new_form_populates_source_dropdown_from_ingestion_datasets(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "source": "binance_btcusdt_1h",
                        "earliest_timestamp": "2024-01-01T00:00:00Z",
                        "latest_timestamp": "2026-01-01T00:00:00Z",
                        "row_count": 1000,
                    },
                    {
                        "source": "reddit_sentiment",
                        "earliest_timestamp": "2025-01-01T00:00:00Z",
                        "latest_timestamp": "2026-06-01T00:00:00Z",
                        "row_count": 42,
                    },
                ]
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")

    assert response.status_code == 200
    assert "binance_btcusdt_1h" in response.text
    assert "reddit_sentiment" in response.text
    assert "No ingested datasets yet" not in response.text


def test_run_new_form_empty_dataset_history_shows_messaging(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json={"items": []})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")

    assert response.status_code == 200
    assert "No ingested datasets yet -- run a crawl first" in response.text
    assert 'name="dataset_reference_source"' not in response.text


def test_run_new_form_dataset_fetch_transport_failure_degrades_to_empty_state(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")

    assert response.status_code == 200
    assert "No ingested datasets yet -- run a crawl first" in response.text
    assert "dataset_id" in response.text


def test_run_new_submit_stored_dataset_reference(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        payload = json.loads(request.read())
        assert payload["dataset_reference"] == {"source": "binance_btcusdt_1h"}
        return httpx.Response(201, json={"id": RUN_ID, "status": "running"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {
        **VALID_FORM,
        "dataset_reference_path": "",
        "dataset_reference_inline": "",
        "dataset_reference_source": "binance_btcusdt_1h",
        "dataset_reference_start": "",
        "dataset_reference_end": "",
        "dataset_reference_field": "",
    }

    response = client.post("/runs/new", data=form, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{RUN_ID}"


# RSS-001: dataset-context summary line ("data-row-count"/"data-earliest"/
# "data-latest" attributes + full-source labeling).


def test_run_new_form_dataset_options_carry_data_attributes(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "source": "binance_btcusdt_1h",
                        "earliest_timestamp": "2024-01-01T00:00:00Z",
                        "latest_timestamp": "2026-01-01T00:00:00Z",
                        "row_count": 1000,
                    },
                ]
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")

    assert response.status_code == 200
    assert 'data-row-count="1000"' in response.text
    assert 'data-earliest="2024-01-01 00:00:00+00:00"' in response.text
    assert 'data-latest="2026-01-01 00:00:00+00:00"' in response.text
    assert 'id="dataset-source-summary"' in response.text
    assert "updateDatasetSourceSummary" in response.text


def test_run_new_form_jinja_render_shows_full_source_label_with_redisplay_values() -> None:
    """RSS-001: `run_new_submit`'s own error-redisplay branches always pass
    `values` populated from the submitted form (including
    `dataset_reference_start`/`_end` whenever the user filled them in) --
    see e.g. `test_run_new_submit_422_from_gateway_api_redisplays_form` above
    for that same `values` mechanism. Since DASH-120, those branches also
    re-fetch and pass the real stored-dataset list (see
    `test_run_new_submit_split_cap_422_preserves_stored_dataset_selection`
    for that real request round-trip) -- this test predates that fix and now
    exercises the same "populated `values.dataset_reference_start`/`_end`"
    plus "a rendered, pre-selected stored-dataset `<option>`" combination via
    a direct, manufactured-context template render instead, which remains a
    valid, narrower check of the template's own "full source" labeling logic
    in isolation from the router.
    """
    from starlette.requests import Request

    from app.main import templates

    scope = {
        "type": "http",
        "method": "GET",
        "path": "/runs/new",
        "raw_path": b"/runs/new",
        "query_string": b"",
        "headers": [],
        "server": ("testserver", 80),
        "scheme": "http",
    }
    request = Request(scope)

    datasets = [
        DatasetSummaryResponse(
            source="binance_btcusdt_1h",
            earliest_timestamp="2024-01-01T00:00:00Z",
            latest_timestamp="2026-01-01T00:00:00Z",
            row_count=1000,
        )
    ]
    values = {
        "dataset_id": "dataset-1",
        "dataset_reference_source": "binance_btcusdt_1h",
        "dataset_reference_start": "2026-01-15",
        "dataset_reference_end": "2026-01-20",
    }

    response = templates.TemplateResponse(
        request, "run_new.html", {"datasets": datasets, "values": values}
    )
    html = response.body.decode()

    assert 'data-row-count="1000"' in html
    assert "selected" in html
    assert 'value="2026-01-15"' in html
    assert 'value="2026-01-20"' in html
    assert "full source" in html


# RSS-002: live, client-side "approximately N splits" estimate.
#
# `computeEstimatedSplits()` is client-side JS with no JS-execution harness in
# this service's default (non-e2e) suite, so per the ticket's own Test
# acceptance criteria these are Jinja-render-level assertions (the function and
# its event-listener wiring are present in the rendered HTML), plus a separate
# Python-side cross-check (below) proving the formula tuples used to reason
# about the JS are correct against `generate_splits`'s own real output -- not a
# test of the JS itself.


def test_run_new_form_wires_compute_estimated_splits(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "source": "binance_btcusdt_1h",
                        "earliest_timestamp": "2024-01-01T00:00:00Z",
                        "latest_timestamp": "2026-01-01T00:00:00Z",
                        "row_count": 79180,
                    },
                ]
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")
    html = response.text

    assert response.status_code == 200
    assert "function computeEstimatedSplits" in html
    assert 'id="estimated-splits"' in html
    assert "fill in a dataset reference to see a split-count estimate" in html.lower()
    # Re-render wiring: the four numeric fields on `input`, the dropdown on
    # `change`, and both dataset-reference fields (path/inline) -- not
    # `horizon` (`generate_splits` takes no horizon param).
    assert 'purgeGapHours.addEventListener("input", computeEstimatedSplits)' in html
    assert 'trainWindow.addEventListener("input", computeEstimatedSplits)' in html
    assert 'testWindow.addEventListener("input", computeEstimatedSplits)' in html
    assert 'step.addEventListener("input", computeEstimatedSplits)' in html
    assert 'path.addEventListener("input", computeEstimatedSplits)' in html
    assert 'inline.addEventListener("input", computeEstimatedSplits)' in html
    assert "computeEstimatedSplits();" in html
    assert "horizon.addEventListener" not in html
    # This estimate must never gate submission -- `checkReference()` remains
    # the only function called from the form's own `submit` listener.
    assert (
        'form.addEventListener("submit", function (event) {\n'
        "        if (!checkReference()) {" in html
    )


def test_run_new_form_estimates_splits_for_inline_and_path_modes(monkeypatch) -> None:
    """RSS-002 originally only estimated splits for the 'stored dataset'
    reference mode -- inline payload and local file path modes got no
    client-side warning at all before hitting validation-service's 500-split
    server cap blind. This closes that gap for inline (row count is
    computable client-side from the parsed JSON) and gives an explicit
    no-estimate-available message for file path (row count isn't readable in
    the browser)."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json={"items": []})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")
    html = response.text

    assert response.status_code == 200
    assert "var MAX_SPLITS = 500;" in html
    assert "function rowCountFromInlinePayload" in html
    assert "function currentRowCount" in html
    assert "exceeds the \" + MAX_SPLITS + \"-split maximum per run" in html
    assert "No split-count estimate available for a local file path" in html


def test_run_new_form_renders_zero_split_warning_branch(monkeypatch) -> None:
    """DH-005: a live estimate of exactly 0 must render a distinct
    `form-status-warn`-styled message, not the pre-DH-005 wording
    ('Approximately 0 split(s) estimated') that read as a valid-but-boring
    result. The over-cap branch's own message/styling is unchanged."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json={"items": []})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")
    html = response.text

    assert response.status_code == 200
    assert "This configuration would produce no splits -- widen the " in html
    assert "dataset's range, reduce train/test window, or reduce purge gap." in html
    assert 'if (estimate === 0) {' in html
    assert 'estimatedSplits.classList.add("form-status-warn");' in html
    # Over-cap branch untouched: same wording/styling as before this ticket.
    assert (
        "exceeds the \" + MAX_SPLITS + \"-split maximum per run" in html
    )


def test_estimated_splits_formula_matches_generate_splits() -> None:
    """Cross-check (Python-side only, not a JS test) that the closed-form
    formula `computeEstimatedSplits()` implements -- and the concrete tuples
    used to reason about it -- match `naive_first_engine.splitting
    .generate_splits`'s own real output for the same synthetic, gapless
    hourly index. Guards against formula drift between this client estimate
    and RSS-004's server-side check, both of which must implement the same
    row-offset semantics (`purge_gap_hours` as a literal row-position offset,
    not a calendar-hour conversion -- OQ-3, disclosed, out of scope).

    Note: the sprint's real incident (`row_count=79180, train_window=360,
    test_window=1540, step=2, purge_gap_hours=24`) produced `38597` splits
    against real ingested data with gaps; a synthetic, gapless
    `pandas.date_range` of the same length instead produces `38629`, which is
    what both the formula and `generate_splits` agree on below.
    """
    import pandas as pd
    from naive_first_engine.splitting import generate_splits

    def estimated_splits(row_count, train_window, test_window, step, purge_gap_hours):
        numerator = row_count - train_window - purge_gap_hours - test_window
        if numerator < 0:
            return 0
        return numerator // step + 1

    cases = [
        (79180, 360, 1540, 2, 24, 38629),
        (1000, 100, 50, 10, 5, 85),
        (50, 100, 10, 1, 0, 0),
    ]
    for row_count, train_window, test_window, step, purge_gap_hours, expected in cases:
        formula_result = estimated_splits(
            row_count, train_window, test_window, step, purge_gap_hours
        )
        assert formula_result == expected

        index = pd.date_range("2020-01-01", periods=row_count, freq="h")
        real_splits = generate_splits(
            index, train_window, test_window, step, purge_gap_hours
        )
        assert len(real_splits) == expected, (
            f"formula/generate_splits drift for {row_count=}, {train_window=}, "
            f"{test_window=}, {step=}, {purge_gap_hours=}"
        )


def test_run_new_submit_stored_dataset_reference_with_range_and_field(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        import json

        payload = json.loads(request.read())
        assert payload["dataset_reference"] == {
            "source": "binance_btcusdt_1h",
            "start": "2026-01-01",
            "end": "2026-02-01",
            "field": "close",
        }
        return httpx.Response(201, json={"id": RUN_ID, "status": "running"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    form = {
        **VALID_FORM,
        "dataset_reference_path": "",
        "dataset_reference_inline": "",
        "dataset_reference_source": "binance_btcusdt_1h",
        "dataset_reference_start": "2026-01-01",
        "dataset_reference_end": "2026-02-01",
        "dataset_reference_field": "close",
    }

    response = client.post("/runs/new", data=form, follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == f"/runs/{RUN_ID}"


# DH-008: Horizon field's dataset-sampling-interval hint (ADR-0007). All three
# branches live in one inline `<script>` block (client-side, mode-switched by
# `currentRowCount()`, the same pattern RSS-001 uses for
# `dataset-source-summary`), so a single render exercises all of them --
# mirrors `test_run_new_form_dataset_options_carry_data_attributes`'s approach
# of asserting on rendered markup/script text rather than executing the JS.


def test_run_new_form_has_horizon_unit_hint_element_and_logic(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json={"items": []})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")

    assert response.status_code == 200
    text = response.text

    # Hint element exists and starts empty/hidden -- no dataset reference
    # selected yet (same no-selection precedent as RSS-001/RSS-002).
    assert 'id="horizon-unit-hint"' in text
    assert "updateHorizonUnitHint" in text

    # Stored-dataset branch: states the sampled interval and restates
    # horizon's meaning in that unit.
    assert "is sampled hourly, so" in text
    assert "hours ahead, not 24 days" in text

    # Local-file-path/inline-payload branch: no fabricated interval.
    assert "whatever the submitted" in text
    assert "data's own timestamp spacing turns out to be" in text

    # Reciprocal pointer to /runs/horizon-summary, accurate against that
    # page's own copy (horizon_summary.html states the days view "assumes
    # the one hourly-sampled source available today").
    assert "/runs/horizon-summary" in text
    assert "assumes hourly sampling" in text

    # Updated tooltip: unit-relative wording, no bare "steps ahead" claim
    # left unqualified.
    assert "not a fixed hour/day unit" in text


def test_run_new_template_has_no_banned_positioning_words() -> None:
    """DH-008: extends the same banned-positioning-word discipline
    `test_horizon_summary_template_has_no_banned_positioning_words`
    (`test_runs_horizon_summary.py`) already applies to `horizon_summary.html`
    to `run_new.html`'s new hint/tooltip copy -- per DH-008's own acceptance
    criteria this checks the three words it names ("optimal," "recommended,"
    "best"); the wider prediction/forecast/signal/target set isn't reused
    here because `run_new.html` already has pre-existing, in-scope-elsewhere
    copy (RSS-001's dataset-field tooltip) using "forecast" to describe what
    a *model* does, not a claim this product predicts -- out of this
    ticket's scope to touch.
    """
    import pathlib

    template_path = (
        pathlib.Path(__file__).parent.parent / "src" / "app" / "templates" / "run_new.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("optimal", "recommended", "best"):
        assert banned not in text, f"banned positioning word {banned!r} found in run_new.html"


# DASH-126 (UAT-002): raw-levels-vs-returns warning made always-visible on
# `run_new.html`, not gated behind the `dataset_reference_field` tooltip's
# hover-only discovery.

RAW_LEVELS_WARNING_SENTENCE = (
    "Note: ingested fields today are raw levels (e.g. price, on-chain metric value), not returns "
    "-- naive-first validation is designed to compare return forecasts. Naive0 (predicts 0) is "
    "nonsensically wrong by construction on raw price levels, so a run against a raw level will "
    "produce a misleadingly favorable verdict that is an artifact of the field choice, not a real "
    "finding. Compute a returns series before validating if you want a meaningful audit."
)


def test_run_new_form_shows_raw_levels_warning_unconditionally_in_body(monkeypatch) -> None:
    """UAT-002 AC1/AC3: the warning renders as static page body text (not
    only inside the `dataset_reference_field` tooltip's `data-tooltip`
    attribute value), regardless of form state -- no hover needed.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "source": "binance_btcusdt_1h",
                        "earliest_timestamp": "2024-01-01T00:00:00Z",
                        "latest_timestamp": "2026-01-01T00:00:00Z",
                        "row_count": 1000,
                    },
                ]
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")
    html = response.text
    normalized = re.sub(r"\s+", " ", html)

    assert response.status_code == 200
    assert RAW_LEVELS_WARNING_SENTENCE in normalized
    # The pre-existing tooltip must still carry the sentence too (AC4: not
    # removed/altered) -- so the body must contain it at least twice: once in
    # the static notice, once inside the tooltip's data-tooltip attribute.
    assert normalized.count(RAW_LEVELS_WARNING_SENTENCE) >= 2
    # Confirm at least one occurrence is outside any data-tooltip attribute --
    # i.e. present as plain visible text, not just inside an attribute value.
    stripped = re.sub(r'data-tooltip=("[^"]*"|\'[^\']*\')', "", normalized)
    assert RAW_LEVELS_WARNING_SENTENCE in stripped
