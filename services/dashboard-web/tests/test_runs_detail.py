"""DASH-004: `GET /runs/{id}` tests.

Fakes gateway-api with `httpx.MockTransport`, mirroring gateway-api's own
`tests/test_runs_routing.py` mocking approach -- `app.routers.runs` builds
`httpx.Client(base_url=base_url)` per-request rather than depending on an
injectable client, so the mock is wired in by monkeypatching `httpx.Client`
itself to substitute a `MockTransport`-backed client instead of a real one,
preserving `base_url` so relative outbound paths still resolve correctly.
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app
from app.routers.runs import CAVEAT_SENTENCE, build_shareable_summary_text
from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

RAW_KEY = "super-secret-raw-api-key-do-not-leak"
RUN_ID = "11111111-1111-1111-1111-111111111111"

RUN_DETAIL_BODY = {
    "id": RUN_ID,
    "tenant_id": "tenant-a",
    "dataset_id": "dataset-1",
    "horizon": 24,
    "purge_gap_hours": 6,
    "split_config": {"train_window": 100, "test_window": 10, "step": 10},
    "status": "completed",
    "created_at": "2026-08-01T00:00:00Z",
    "completed_at": "2026-08-01T01:00:00Z",
    "failure_reason": None,
}

SPLIT_BODY = {
    "split_index": 0,
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

# RAV-003: a second split, with a documented-undefined DM statistic (a
# single-test-point split -- both dm_statistic and dm_pvalue null).
UNDEFINED_DM_SPLIT_BODY = {
    **SPLIT_BODY,
    "split_index": 1,
    "dm_statistic": None,
    "dm_pvalue": None,
    "dm_verdict": "no significant difference",
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


def test_run_detail_success_with_splits(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert RUN_ID in response.text
    assert "completed" in response.text
    assert "no significant difference" in response.text
    assert "1.1" in response.text

    # RAV-002: the error-by-split chart renders as inline SVG (ADR-0006) and
    # its bars carry the real model_mae/naive0_mae values from this fixture.
    assert "<svg" in response.text
    assert "1.1" in response.text  # model_mae
    assert "1.0" in response.text  # naive0_mae


def test_run_detail_metric_query_param_switches_chart(monkeypatch) -> None:
    """RAV-004: `?metric=smape` re-renders the chart with sMAPE's own
    model/naive0 values, not MAE's.
    """
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}", params={"metric": "smape"})

    assert response.status_code == 200
    assert "sMAPE" in response.text
    assert "3.3" in response.text  # model_smape
    assert "3.0" in response.text  # naive0_smape


def test_run_detail_invalid_metric_falls_back_to_mae(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}", params={"metric": "not-a-real-metric"})

    assert response.status_code == 200
    assert "(MAE)" in response.text
    assert "1.1" in response.text  # model_mae


def test_run_detail_metric_selector_offers_all_seven_metrics(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    for value in ("mae", "rmse", "smape", "mase", "da", "f1", "oos_r2"):
        assert f'value="{value}"' in response.text
    assert "Directional accuracy" in response.text
    assert ">F1<" in response.text


def test_run_detail_running_with_no_splits(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            body = {**RUN_DETAIL_BODY, "status": "running", "completed_at": None}
            return httpx.Response(200, json=body)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert "running" in response.text
    assert "No per-split validation results yet" in response.text

    # RAV-002: a zero-split run must not render the chart -- the new
    # `{% include %}` lives inside the existing `{% if splits %}` branch, not
    # before it.
    assert "<svg" not in response.text


def test_run_detail_404(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"detail": "not found"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 404
    assert "not found" in response.text.lower()


def test_run_detail_502_from_gateway_api(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "downstream service unavailable"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "downstream service unavailable" not in response.text


def test_run_detail_504_from_gateway_api(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(504, json={"detail": "downstream service timed out"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text
    assert "downstream service timed out" not in response.text


def test_run_detail_transport_connect_error(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ConnectError("connection refused", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "connection refused" not in response.text


def test_run_detail_transport_timeout(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.TimeoutException("timed out", request=request)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 504
    assert "results currently unavailable" in response.text


def test_run_detail_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get(f"/runs/{RUN_ID}", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def test_run_detail_template_has_no_banned_positioning_words() -> None:
    """FHS-003's new partial's own *filename*
    (`_forecast_horizon_summary_panel.html`) is `{% include %}`-ed here, and
    the internal ticket/feature name ("Forecast Horizon Summary") legitimately
    contains the word "forecast" -- that is a structural template reference,
    not rendered product copy, so `{% include ... %}` statements are stripped
    before scanning (the new partial's own *content* gets its own,
    non-stripped scan below).
    """
    import re

    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "run_detail.html"
    )
    text = re.sub(r"\{%\s*include\s+.*?%\}", "", template_path.read_text(encoding="utf-8")).lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in run_detail.html"


def test_error_chart_partial_has_no_banned_positioning_words() -> None:
    """RAV-002: `_error_chart.html` is a new template this ticket adds, so it
    gets its own copy of `run_detail.html`'s existing banned-word scan rather
    than assuming inclusion into an already-checked template is enough
    (Jinja `{% include %}` output isn't re-scanned by the test above, since
    that test reads the template *source* file, not the rendered response).
    """
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "_error_chart.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in _error_chart.html"


def test_dm_verdict_chart_partial_has_no_banned_positioning_words() -> None:
    """RAV-003: same banned-word scan pattern as RAV-002's above, applied to
    the new `_dm_verdict_chart.html` partial.
    """
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "_dm_verdict_chart.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, (
            f"banned positioning word {banned!r} found in _dm_verdict_chart.html"
        )


def test_run_detail_renders_dm_verdict_chart_with_undefined_category(monkeypatch) -> None:
    """RAV-003: a run with one real-verdict split and one split whose
    dm_statistic/dm_pvalue are both null renders both the real verdict string
    and the "undefined for this split" copy -- the null case is never dropped
    or silently merged into "no significant difference".
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY, UNDEFINED_DM_SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert "no significant difference" in response.text
    assert "undefined for this split" in response.text
    assert "dm-verdict-chart-svg" in response.text


def test_run_detail_running_with_no_splits_renders_neither_chart(monkeypatch) -> None:
    """RAV-003: extends the existing zero-splits assertion (RAV-002's own
    `test_run_detail_running_with_no_splits`) to also confirm this ticket's
    new chart is absent, not just RAV-002's.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            body = {**RUN_DETAIL_BODY, "status": "running", "completed_at": None}
            return httpx.Response(200, json=body)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert "<svg" not in response.text
    assert "dm-verdict-chart-svg" not in response.text
    assert "error-chart-svg" not in response.text


def test_forecast_horizon_summary_panel_partial_has_no_banned_positioning_words() -> None:
    """FHS-003: same banned-word scan pattern as RAV-002/003's above, applied
    to the new `_forecast_horizon_summary_panel.html` partial.
    """
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "_forecast_horizon_summary_panel.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "target", "recommendation"):
        assert banned not in text, (
            f"banned positioning word {banned!r} found in "
            "_forecast_horizon_summary_panel.html"
        )


def test_run_detail_renders_forecast_horizon_summary_panel_with_real_metrics(
    monkeypatch,
) -> None:
    """FHS-003: the panel renders the fixture's real model_mae/naive0_mae and
    the real dm_verdict/dm_pvalue for a split with a defined DM statistic.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert "horizon-summary-table" in response.text
    assert "Per-split validation summary" in response.text
    assert "verdict-label-no-sig-diff" in response.text
    assert "0.42" in response.text  # dm_pvalue


def test_run_detail_forecast_horizon_summary_panel_renders_undefined_category(
    monkeypatch,
) -> None:
    """FHS-003: a split with dm_statistic=None, dm_pvalue=None renders the
    UNDEFINED_VERDICT_CATEGORY label in the panel, distinct from -- not
    merged into -- "no significant difference", and not dropped.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY, UNDEFINED_DM_SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert 'class="verdict-label-undefined"' in response.text
    assert "undefined for this split" in response.text
    # both categories present, and each on its own row -- undefined split's
    # verdict is never coerced into the defined split's "no significant
    # difference" label.
    assert response.text.count('class="verdict-label-no-sig-diff"') >= 1
    assert response.text.count('class="verdict-label-undefined"') >= 1


def test_run_detail_running_with_no_splits_does_not_render_horizon_summary_panel(
    monkeypatch,
) -> None:
    """FHS-003: a zero-split run continues to render the existing "no
    results yet" state, not a broken/empty summary panel.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            body = {**RUN_DETAIL_BODY, "status": "running", "completed_at": None}
            return httpx.Response(200, json=body)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert "No per-split validation results yet" in response.text
    assert "horizon-summary-table" not in response.text


def test_build_shareable_summary_text_contains_caveat_verbatim() -> None:
    """FHS-004: the regression-proof test the ticket's own instruction calls
    for -- exact string match of the caveat sentence, not a substring/keyword
    check, so a future edit that silently weakens the wording is caught.
    """
    run = RunDetailResponse(**RUN_DETAIL_BODY)
    split = SplitResultResponse(**SPLIT_BODY)

    text = build_shareable_summary_text(run, [split])

    assert CAVEAT_SENTENCE in text
    assert (
        CAVEAT_SENTENCE == "This is a backtested validation result, not a forecast of "
        "future performance. Under this platform's own published research, no machine "
        "learning model has beaten a naive statistical baseline in a stable, significant "
        "way at any tested horizon -- treat any deviation shown here as unproven until "
        "independently reconfirmed."
    )


def test_build_shareable_summary_text_contains_real_identifiers_and_metrics() -> None:
    """FHS-004: the returned text contains the real dataset/run identifier,
    the real naive/model metric values, and the real DM verdict/p-value.
    """
    run = RunDetailResponse(**RUN_DETAIL_BODY)
    split = SplitResultResponse(**SPLIT_BODY)

    text = build_shareable_summary_text(run, [split])

    assert RUN_ID in text
    assert "dataset-1" in text
    assert "1.1" in text  # model_mae
    assert "1.0" in text  # naive0_mae
    assert "no significant difference" in text
    assert "0.42" in text  # dm_pvalue


def test_build_shareable_summary_text_horizon_168_shows_7_days() -> None:
    """FHS-004: horizon=168 (ADR-0007's reverse conversion) shows "7 days"."""
    run = RunDetailResponse(**{**RUN_DETAIL_BODY, "horizon": 168})
    split = SplitResultResponse(**SPLIT_BODY)

    text = build_shareable_summary_text(run, [split])

    assert "7 days" in text


def test_build_shareable_summary_text_unknown_horizon_shows_raw_value_only() -> None:
    """FHS-004: a horizon not matching 168/360/720 shows the raw value, no
    fabricated day label (ADR-0007's "no silent generalization" note).
    """
    run = RunDetailResponse(**{**RUN_DETAIL_BODY, "horizon": 42})
    split = SplitResultResponse(**SPLIT_BODY)

    text = build_shareable_summary_text(run, [split])

    assert "42" in text
    assert "days" not in text


def test_run_detail_renders_shareable_summary_textarea(monkeypatch) -> None:
    """FHS-004: `GET /runs/{run_id}` includes the `<textarea>` with the
    summary text when splits exist.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert "<textarea" in response.text
    assert "readonly" in response.text
    import html

    assert CAVEAT_SENTENCE in html.unescape(response.text)


def test_shareable_summary_partial_has_no_banned_positioning_words_outside_caveat() -> None:
    """FHS-004: banned-positioning-words scan, extended for the new partial --
    permits only the caveat's own negated "forecast" usage, flags any other
    occurrence of the banned words.
    """
    import re

    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "_shareable_summary.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()
    text_without_caveat = text.replace(CAVEAT_SENTENCE.lower(), "")

    for banned in ("prediction", "forecast", "signal", "target", "recommendation"):
        assert banned not in text_without_caveat, (
            f"banned positioning word {banned!r} found in _shareable_summary.html "
            "outside the caveat sentence"
        )


def test_style_css_dm_verdict_colors_never_pair_pure_red_and_pure_green() -> None:
    """RAV-003 color-safety check: reads the actual CSS variable values used
    by the four DM-verdict categories and confirms none is a canonical pure
    red paired with a canonical pure green (the exact bull/bear pairing
    CLAUDE.md's positioning constraint forbids).
    """
    import re

    style_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "static"
        / "style.css"
    )
    text = style_path.read_text(encoding="utf-8")

    variable_values = dict(re.findall(r"(--color-[\w-]+):\s*(#[0-9a-fA-F]{3,8})", text))

    verdict_vars = [
        "--color-status-completed-text",  # "better"
        "--color-status-failed-text",  # "worse"
        "--color-status-running-text",  # "no significant difference"
        "--color-text-muted",  # "undefined for this split"
    ]
    hex_values = [variable_values[var].lower() for var in verdict_vars]

    _pure_red = {"#f00", "#ff0000"}
    _pure_green = {"#0f0", "#00ff00"}

    assert not (set(hex_values) & _pure_red), "a verdict color is canonical pure red"
    assert not (set(hex_values) & _pure_green), "a verdict color is canonical pure green"
    # No pairing of a red-family and green-family hex among the four at all.
    reds = [v for v in hex_values if v in _pure_red]
    greens = [v for v in hex_values if v in _pure_green]
    assert not (reds and greens), "verdict colors pair a pure red with a pure green"


CLIENT_BASELINE_DISCLAIMER = (
    "This client-supplied baseline is shown for reference only and is not "
    "validated by this platform."
)

CLIENT_BASELINE_BODY = {
    "key": "client",
    "mae": 0.9,
    "rmse": 1.0,
    "smape": 1.0,
    "mase": 1.0,
    "da": 0.5,
    "f1": 0.5,
    "oos_r2": 0.1,
    "dm_statistic": -1.2,
    "dm_pvalue": 0.03,
    "dm_verdict": "better",
    "disclaimer": CLIENT_BASELINE_DISCLAIMER,
}

SPLIT_BODY_WITH_CLIENT_BASELINE = {
    **SPLIT_BODY,
    "client_baseline": CLIENT_BASELINE_BODY,
}


def test_run_detail_renders_client_baseline_disclaimer_when_present(monkeypatch) -> None:
    """RAV-005: `client_baseline.disclaimer` renders verbatim, adjacent to the
    chart, when at least one split carries a `client_baseline`.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY_WITH_CLIENT_BASELINE])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert CLIENT_BASELINE_DISCLAIMER in response.text


def test_run_detail_omits_client_baseline_disclaimer_when_absent(monkeypatch) -> None:
    """No split carries a `client_baseline` (the common case) -- the
    disclaimer copy must not render at all.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == f"/runs/{RUN_ID}":
            return httpx.Response(200, json=RUN_DETAIL_BODY)
        if request.url.path == f"/runs/{RUN_ID}/splits":
            return httpx.Response(200, json=[SPLIT_BODY])
        raise AssertionError(f"unexpected path {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/{RUN_ID}")

    assert response.status_code == 200
    assert CLIENT_BASELINE_DISCLAIMER not in response.text
    assert "bar-client" not in response.text


def test_style_css_client_baseline_color_not_a_red_green_pairing() -> None:
    """RAV-005 color-safety check, extended: the new third-series color token
    (`--color-accent-3`) must not be a canonical pure red or pure green, and
    must not pair with a pure red/green among the existing verdict colors.
    """
    import re

    style_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "static"
        / "style.css"
    )
    text = style_path.read_text(encoding="utf-8")

    variable_values = dict(re.findall(r"(--color-[\w-]+):\s*(#[0-9a-fA-F]{3,8})", text))

    _pure_red = {"#f00", "#ff0000"}
    _pure_green = {"#0f0", "#00ff00"}

    client_color = variable_values["--color-accent-3"].lower()
    assert client_color not in _pure_red, "client-baseline color is canonical pure red"
    assert client_color not in _pure_green, "client-baseline color is canonical pure green"

    verdict_vars = [
        "--color-status-completed-text",
        "--color-status-failed-text",
        "--color-status-running-text",
        "--color-text-muted",
    ]
    other_hex_values = [variable_values[var].lower() for var in verdict_vars]
    assert client_color not in other_hex_values, (
        "client-baseline color duplicates an existing verdict-category color"
    )
