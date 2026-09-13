"""RAV-009: `GET /runs/trend` tests.

Fakes gateway-api with `httpx.MockTransport`, mirroring
`tests/test_runs_horizon_summary.py`'s mocking approach -- `app.routers.runs`
builds `httpx.Client(base_url=base_url)` per-request rather than depending on
an injectable client, so the mock is wired in by monkeypatching `httpx.Client`
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

RUN_COMPLETED_1 = {
    "id": "11111111-1111-1111-1111-111111111111",
    "dataset_id": "dataset-1",
    "horizon": 24,
    "status": "completed",
    "created_at": "2026-08-01T00:00:00Z",
    "completed_at": "2026-08-01T01:00:00Z",
}

RUN_COMPLETED_2 = {
    "id": "22222222-2222-2222-2222-222222222222",
    "dataset_id": "dataset-1",
    "horizon": 24,
    "status": "completed",
    "created_at": "2026-08-02T00:00:00Z",
    "completed_at": "2026-08-02T01:00:00Z",
}

RUN_RUNNING = {
    "id": "33333333-3333-3333-3333-333333333333",
    "dataset_id": "dataset-1",
    "horizon": 24,
    "status": "running",
    "created_at": "2026-08-03T00:00:00Z",
    "completed_at": None,
}

RUN_OTHER_GROUP = {
    "id": "44444444-4444-4444-4444-444444444444",
    "dataset_id": "dataset-2",
    "horizon": 720,
    "status": "completed",
    "created_at": "2026-08-04T00:00:00Z",
    "completed_at": "2026-08-04T01:00:00Z",
}

RUNS_BODY = {
    "items": [RUN_COMPLETED_1, RUN_COMPLETED_2, RUN_RUNNING, RUN_OTHER_GROUP],
    "limit": 50,
    "offset": 0,
    "total": 4,
}

_SPLIT_FIELDS = {
    "train_start": "2026-01-01T00:00:00Z",
    "train_end": "2026-01-10T00:00:00Z",
    "purge_start": "2026-01-10T00:00:00Z",
    "purge_end": "2026-01-10T06:00:00Z",
    "test_start": "2026-01-10T06:00:00Z",
    "test_end": "2026-01-11T00:00:00Z",
    "model_rmse": 2.2,
    "model_smape": 3.3,
    "model_mase": 4.4,
    "model_da": 0.5,
    "model_f1": 0.6,
    "model_oos_r2": 0.1,
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


def _split(split_index: int, model_mae: float, naive0_mae: float) -> dict:
    return {
        "split_index": split_index,
        "model_mae": model_mae,
        "naive0_mae": naive0_mae,
        **_SPLIT_FIELDS,
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


def test_trend_no_group_selected_shows_only_selector(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/runs"
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/trend")

    assert response.status_code == 200
    assert "dataset-1 / horizon 24" in response.text
    assert "dataset-2 / horizon 720" in response.text
    assert RUN_COMPLETED_1["id"] not in response.text


def test_trend_selecting_group_fetches_splits_for_completed_runs_only(monkeypatch) -> None:
    split_calls: list[str] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs":
            return httpx.Response(200, json=RUNS_BODY)
        if request.url.path.endswith("/splits"):
            split_calls.append(request.url.path)
            run_id = request.url.path.split("/")[2]
            if run_id == RUN_COMPLETED_1["id"]:
                return httpx.Response(200, json=[_split(0, model_mae=1.0, naive0_mae=2.0)])
            if run_id == RUN_COMPLETED_2["id"]:
                return httpx.Response(200, json=[_split(0, model_mae=3.0, naive0_mae=4.0)])
        raise AssertionError(f"unexpected call: {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/trend?dataset_id=dataset-1&horizon=24&metric=mae")

    assert response.status_code == 200
    # Only the two completed runs' splits are fetched -- the running run is skipped.
    assert len(split_calls) == 2
    assert f"/runs/{RUN_RUNNING['id']}/splits" not in split_calls
    assert RUN_COMPLETED_1["id"] in response.text
    assert RUN_COMPLETED_2["id"] in response.text
    assert RUN_RUNNING["id"] not in response.text


def test_trend_consistency_indicator_renders_correct_ratio(monkeypatch) -> None:
    """RAV-010: route-level test -- the indicator's rendered text matches the
    fixture's known N/M values, reusing RAV-009's already-fetched per-run
    split data (no extra `/splits` calls beyond the two already asserted by
    the RAV-009 test above).
    """

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs":
            return httpx.Response(200, json=RUNS_BODY)
        if request.url.path.endswith("/splits"):
            run_id = request.url.path.split("/")[2]
            if run_id == RUN_COMPLETED_1["id"]:
                # Majority "better" -> counts as a beat.
                return httpx.Response(
                    200,
                    json=[
                        {**_split(0, model_mae=1.0, naive0_mae=2.0), "dm_verdict": "better",
                         "dm_statistic": -2.0, "dm_pvalue": 0.01},
                    ],
                )
            if run_id == RUN_COMPLETED_2["id"]:
                # Majority "worse" -> does not count as a beat.
                return httpx.Response(
                    200,
                    json=[
                        {**_split(0, model_mae=3.0, naive0_mae=4.0), "dm_verdict": "worse",
                         "dm_statistic": 2.0, "dm_pvalue": 0.01},
                    ],
                )
        raise AssertionError(f"unexpected call: {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/trend?dataset_id=dataset-1&horizon=24&metric=mae")

    assert response.status_code == 200
    assert "Beat Naive0 in 1 of 2 completed runs" in response.text


def test_trend_consistency_indicator_no_group_selected_shows_no_data(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/trend")

    assert response.status_code == 200
    assert "No completed runs matched this selection." in response.text
    assert "0 of 0" not in response.text


def test_trend_zero_matching_group_renders_no_chart(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=RUNS_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/trend?dataset_id=dataset-missing&horizon=1&metric=mae")

    assert response.status_code == 200
    assert "<svg" not in response.text


def test_trend_502_from_gateway_api_reuses_error_template(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(502, json={"detail": "downstream service unavailable"})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/trend")

    assert response.status_code == 502
    assert "results currently unavailable" in response.text
    assert "downstream service unavailable" not in response.text


def test_trend_requires_session(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("gateway-api must not be called without a session")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)

    response = client.get("/runs/trend", follow_redirects=False)

    assert response.status_code == 303
    assert response.headers["location"] == "/login"


def _make_run(index: int, dataset_id: str = "dataset-1", horizon: int = 24) -> dict:
    return {
        "id": f"run-{index:04d}-0000-0000-0000-000000000000",
        "dataset_id": dataset_id,
        "horizon": horizon,
        "status": "completed",
        "created_at": f"2026-08-{(index % 28) + 1:02d}T00:00:00Z",
        "completed_at": f"2026-08-{(index % 28) + 1:02d}T01:00:00Z",
    }


def test_trend_group_selector_sees_runs_beyond_the_old_default_20_limit(monkeypatch) -> None:
    """DASH-122 regression: prior to this fix, `runs_trend` called `GET /runs`
    with no explicit `limit`, silently getting only the endpoint's own
    `limit=20` default -- with 25 runs in the group, the 21st-25th would
    never appear in the group selector. All 25 fit in one
    `_RUNS_LIST_PAGE_SIZE=100` page, so this also proves the simple case (not
    just the >100 pagination case below).
    """
    runs = [_make_run(i) for i in range(25)]
    body = {"items": runs, "limit": 100, "offset": 0, "total": 25}

    calls: list[dict] = []

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs":
            calls.append(dict(request.url.params))
            return httpx.Response(200, json=body)
        if request.url.path.endswith("/splits"):
            return httpx.Response(200, json=[_split(0, model_mae=1.0, naive0_mae=2.0)])
        raise AssertionError(f"unexpected call: {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/trend")

    assert response.status_code == 200
    assert len(calls) == 1
    assert calls[0]["limit"] == "100"

    response = client.get(f"/runs/trend?dataset_id=dataset-1&horizon=24&metric=mae")
    assert response.status_code == 200
    for run in runs[20:25]:
        assert run["id"] in response.text


def test_trend_pages_through_more_than_one_hundred_runs(monkeypatch) -> None:
    """DASH-122 regression: validation-service's `GET /runs` hard-caps
    `limit` at 100 (`le=100`, a real `422` above it) -- a tenant/group with
    more than 100 runs needs more than one page. This proves `runs_trend`
    actually pages through `offset=0`/`offset=100` and its consistency
    indicator/trend chart reflect runs beyond the first page.
    """
    runs = [_make_run(i) for i in range(150)]
    total = len(runs)

    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs":
            limit = int(request.url.params["limit"])
            offset = int(request.url.params["offset"])
            assert limit == 100
            page = runs[offset : offset + limit]
            return httpx.Response(
                200, json={"items": page, "limit": limit, "offset": offset, "total": total}
            )
        if request.url.path.endswith("/splits"):
            return httpx.Response(
                200,
                json=[
                    {**_split(0, model_mae=1.0, naive0_mae=2.0), "dm_verdict": "better",
                     "dm_statistic": -2.0, "dm_pvalue": 0.01},
                ],
            )
        raise AssertionError(f"unexpected call: {request.url.path}")

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/trend?dataset_id=dataset-1&horizon=24&metric=mae")

    assert response.status_code == 200
    # 121st-125th runs (index 120-124) live only on the second page (offset=100).
    for run in runs[120:125]:
        assert run["id"] in response.text
    assert "Beat Naive0 in 150 of 150 completed runs" in response.text


def test_trend_template_has_no_banned_positioning_words() -> None:
    template_path = (
        pathlib.Path(__file__).parent.parent / "src" / "app" / "templates" / "runs_trend.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in text, f"banned positioning word {banned!r} found in runs_trend.html"
