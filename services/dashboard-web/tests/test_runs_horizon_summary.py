"""FHS-002: `GET /runs/horizon-summary` tests.

Fakes gateway-api with `httpx.MockTransport`, mirroring
`tests/test_runs_detail.py`'s mocking approach -- `app.routers.runs` builds
`httpx.Client(base_url=base_url)` per-request rather than depending on an
injectable client, so the mock is wired in by monkeypatching `httpx.Client`
itself to substitute a `MockTransport`-backed client instead of a real one.
"""

from __future__ import annotations

import pathlib

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"

RUN_HORIZON_168 = {
    "id": "11111111-1111-1111-1111-111111111111",
    "tenant_id": "tenant-a",
    "dataset_id": "dataset-1",
    "horizon": 168,
    "status": "completed",
    "created_at": "2026-08-01T00:00:00Z",
    "completed_at": "2026-08-01T01:00:00Z",
}

RUN_HORIZON_720 = {
    "id": "22222222-2222-2222-2222-222222222222",
    "tenant_id": "tenant-a",
    "dataset_id": "dataset-2",
    "horizon": 720,
    "status": "completed",
    "created_at": "2026-08-02T00:00:00Z",
    "completed_at": "2026-08-02T01:00:00Z",
}

RUNS_BODY = {
    "items": [RUN_HORIZON_168, RUN_HORIZON_720],
    "limit": 50,
    "offset": 0,
    "total": 2,
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
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_horizon_summary_no_days_shows_only_selector(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called until a horizon is selected")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary")

    assert response.status_code == 200
    assert "7 days" in response.text
    assert "15 days" in response.text
    assert "30 days" in response.text
    assert RUN_HORIZON_168["id"] not in response.text


def test_horizon_summary_days_7_shows_only_horizon_168_run(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        assert request.url.path == "/runs"
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=7")

    assert response.status_code == 200
    assert RUN_HORIZON_168["id"] in response.text
    assert RUN_HORIZON_720["id"] not in response.text


def test_horizon_summary_out_of_range_days_rejected_with_422(monkeypatch) -> None:
    """QA-found (Sprint 31 UAT sweep): an out-of-range `days` (not one of
    `HORIZON_SUMMARY_DAY_OPTIONS` -- 7/15/30) used to silently render 200 with
    no active day-tab and an empty `runs` list, indistinguishable from "no
    completed runs at a valid horizon". Now rejected up front with a 422, and
    gateway-api must never even be called.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called for an out-of-range 'days'")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    for out_of_range_days in (999, -1):
        response = client.get(f"/runs/horizon-summary?days={out_of_range_days}")
        assert response.status_code == 422


def test_horizon_summary_days_zero_and_non_integer_rejected(monkeypatch) -> None:
    """QA regression: `days=0` (falsy but still a value the user explicitly
    set) and a non-integer `days` (FastAPI's own query coercion failure, not
    the `not in HORIZON_SUMMARY_DAY_OPTIONS` guard) must both be rejected
    before gateway-api is ever called, same as any other out-of-range value.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called for an invalid 'days'")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=0")
    assert response.status_code == 422

    response = client.get("/runs/horizon-summary?days=not-a-number")
    assert response.status_code == 422


def test_horizon_summary_days_30_shows_disjoint_set(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=30")

    assert response.status_code == 200
    assert RUN_HORIZON_720["id"] in response.text
    assert RUN_HORIZON_168["id"] not in response.text


def test_horizon_summary_excludes_non_completed_runs_at_matching_horizon(monkeypatch) -> None:
    """FHS-002 bug fix (found in Sprint 27 QA): a `running`/`failed` run at
    the matching horizon is not backtested-validation evidence yet and must
    not appear on this page -- `runs_horizon_summary` filters on both
    `horizon` AND `status == "completed"`, not `horizon` alone.
    """
    running_run = {**RUN_HORIZON_168, "id": "33333333-3333-3333-3333-333333333333", "status": "running", "completed_at": None}
    failed_run = {**RUN_HORIZON_168, "id": "44444444-4444-4444-4444-444444444444", "status": "failed", "completed_at": None}
    body = {
        "items": [running_run, failed_run],
        "limit": 50,
        "offset": 0,
        "total": 2,
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=body)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=7")

    assert response.status_code == 200
    assert running_run["id"] not in response.text
    assert failed_run["id"] not in response.text
    assert "No completed runs at this horizon yet" in response.text


def test_horizon_summary_zero_matches_renders_empty_state(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=15")

    assert response.status_code == 200
    assert "No completed runs at this horizon yet" in response.text
    assert "/runs/new" in response.text
    assert "<table" not in response.text


def test_horizon_summary_502_from_gateway_api_reuses_error_template(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "downstream service unavailable"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=7")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "downstream service unavailable" not in response.text


def test_horizon_summary_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get("/runs/horizon-summary", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def _make_run(index: int, horizon: int = 168, status: str = "completed") -> dict:
    return {
        "id": f"run-{index:04d}-0000-0000-0000-000000000000",
        "tenant_id": "tenant-a",
        "dataset_id": "dataset-1",
        "horizon": horizon,
        "status": status,
        "created_at": f"2026-08-{(index % 28) + 1:02d}T00:00:00Z",
        "completed_at": f"2026-08-{(index % 28) + 1:02d}T01:00:00Z",
    }


def test_horizon_summary_sees_runs_beyond_the_old_default_20_limit(monkeypatch) -> None:
    """DASH-122 regression: prior to this fix, `runs_horizon_summary` called
    `GET /runs` with no explicit `limit`, silently getting only the endpoint's
    own `limit=20` default -- a tenant with 25 runs at the matching horizon
    would never see the 21st-25th on this page. All 25 fit in one
    `_RUNS_LIST_PAGE_SIZE=100` page, so this also proves the simple case (not
    just the >100 pagination case below).
    """
    runs = [_make_run(i) for i in range(25)]
    body = {"items": runs, "limit": 100, "offset": 0, "total": 25}

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/runs"
        calls.append(dict(request.url.params))
        return httpx.Response(200, json=body)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=7")

    assert response.status_code == 200
    for run in runs[20:25]:
        assert run["id"] in response.text
    assert len(calls) == 1
    assert calls[0]["limit"] == "100"


def test_horizon_summary_pages_through_more_than_one_hundred_runs(monkeypatch) -> None:
    """DASH-122 regression: validation-service's `GET /runs` hard-caps
    `limit` at 100 (`le=100`, a real `422` above it) -- a tenant with more
    than 100 runs needs more than one page. This proves `runs_horizon_summary`
    actually pages through `offset=0`/`offset=100` rather than stopping at
    the first page.
    """
    runs = [_make_run(i) for i in range(150)]
    total = len(runs)

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/runs"
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        assert limit == 100
        page = runs[offset : offset + limit]
        return httpx.Response(
            200, json={"items": page, "limit": limit, "offset": offset, "total": total}
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=7")

    assert response.status_code == 200
    # 121st-125th runs (index 120-124) live only on the second page (offset=100).
    for run in runs[120:125]:
        assert run["id"] in response.text


RUN_HORIZON_1H = {
    "id": "55555555-5555-5555-5555-555555555555",
    "tenant_id": "tenant-a",
    "dataset_id": "dataset-3",
    "horizon": 1,
    "status": "completed",
    "created_at": "2026-08-03T00:00:00Z",
    "completed_at": "2026-08-03T01:00:00Z",
}

RUN_HORIZON_6H = {
    "id": "66666666-6666-6666-6666-666666666666",
    "tenant_id": "tenant-a",
    "dataset_id": "dataset-3",
    "horizon": 6,
    "status": "completed",
    "created_at": "2026-08-04T00:00:00Z",
    "completed_at": "2026-08-04T01:00:00Z",
}

RUN_HORIZON_24H = {
    "id": "77777777-7777-7777-7777-777777777777",
    "tenant_id": "tenant-a",
    "dataset_id": "dataset-3",
    "horizon": 24,
    "status": "completed",
    "created_at": "2026-08-05T00:00:00Z",
    "completed_at": "2026-08-05T01:00:00Z",
}

HOUR_RUNS_BODY = {
    "items": [RUN_HORIZON_1H, RUN_HORIZON_6H, RUN_HORIZON_24H],
    "limit": 50,
    "offset": 0,
    "total": 3,
}


@pytest.mark.parametrize(
    "hours,expected_run,other_runs",
    [
        (1, RUN_HORIZON_1H, [RUN_HORIZON_6H, RUN_HORIZON_24H]),
        (6, RUN_HORIZON_6H, [RUN_HORIZON_1H, RUN_HORIZON_24H]),
        (24, RUN_HORIZON_24H, [RUN_HORIZON_1H, RUN_HORIZON_6H]),
    ],
)
def test_horizon_summary_hour_bucket_filters_by_literal_horizon(
    monkeypatch, hours, expected_run, other_runs
) -> None:
    """UAT-010: selecting an hour bucket filters by the literal `horizon`
    value (1/6/24), no conversion -- matching the day-bucket tests' pattern.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=HOUR_RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get(f"/runs/horizon-summary?unit=hours&hours={hours}")

    assert response.status_code == 200
    assert expected_run["id"] in response.text
    for run in other_runs:
        assert run["id"] not in response.text


def test_horizon_summary_hour_bucket_out_of_range_rejected_with_422(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called for an out-of-range 'hours'")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?unit=hours&hours=999")
    assert response.status_code == 422


def test_horizon_summary_unsupported_unit_rejected_with_422(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called for an unsupported 'unit'")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?unit=weeks&hours=1")
    assert response.status_code == 422


def test_horizon_summary_no_selection_shows_both_selectors(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called until a bucket is selected")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary")

    assert response.status_code == 200
    assert "1h" in response.text
    assert "6h" in response.text
    assert "24h" in response.text
    assert "7 days" in response.text


def test_horizon_summary_day_bucket_behavior_unchanged_when_unit_defaults(monkeypatch) -> None:
    """UAT-010: existing day-bucket behavior byte-identical to before -- same
    assertions as `test_horizon_summary_days_7_shows_only_horizon_168_run`."""

    def handler(request: httpx.Request) -> httpx.Response:
        assert request.headers["authorization"] == f"Bearer {RAW_KEY}"
        assert request.url.path == "/runs"
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/horizon-summary?days=7")

    assert response.status_code == 200
    assert RUN_HORIZON_168["id"] in response.text
    assert RUN_HORIZON_720["id"] not in response.text


def test_horizon_summary_template_has_no_banned_positioning_words() -> None:
    template_path = (
        pathlib.Path(__file__).parent.parent / "src" / "app" / "templates" / "horizon_summary.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "target", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in horizon_summary.html"
