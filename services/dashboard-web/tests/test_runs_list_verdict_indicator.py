"""RAV-013: `runs_list.html`'s new "Benchmark comparison" verdict column.

The sprint's own required test: a fixture set of runs with known
split-verdict distributions renders the correct verdict category/label per
row, **including a zero-split run** rendering a plain "no results yet" state,
never a fabricated category. Reuses the same `_patch_transport`-style
`httpx.Client` monkeypatch as `test_runs_list.py`/`test_runs_list_splits_
summary.py` (this router builds `httpx.Client(base_url=...)` per-request
rather than depending on an injectable client).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"

RUN_ID_BETTER = "11111111-1111-1111-1111-111111111111"
RUN_ID_WORSE = "22222222-2222-2222-2222-222222222222"
RUN_ID_MIXED = "33333333-3333-3333-3333-333333333333"
RUN_ID_ZERO_SPLITS = "44444444-4444-4444-4444-444444444444"

RUNS_LIST_BODY = {
    "items": [
        {
            "id": RUN_ID_BETTER,
            "dataset_id": "dataset-1",
            "horizon": 24,
            "status": "completed",
            "created_at": "2026-08-04T00:00:00Z",
            "completed_at": "2026-08-04T01:00:00Z",
        },
        {
            "id": RUN_ID_WORSE,
            "dataset_id": "dataset-2",
            "horizon": 6,
            "status": "completed",
            "created_at": "2026-08-03T00:00:00Z",
            "completed_at": "2026-08-03T01:00:00Z",
        },
        {
            "id": RUN_ID_MIXED,
            "dataset_id": "dataset-3",
            "horizon": 1,
            "status": "completed",
            "created_at": "2026-08-02T00:00:00Z",
            "completed_at": "2026-08-02T01:00:00Z",
        },
        {
            "id": RUN_ID_ZERO_SPLITS,
            "dataset_id": "dataset-4",
            "horizon": 1,
            "status": "running",
            "created_at": "2026-08-01T00:00:00Z",
            "completed_at": None,
        },
    ],
    "limit": 50,
    "offset": 0,
    "total": 4,
}

_BASE_SPLIT_FIELDS = {
    "train_start": "2026-01-01T00:00:00",
    "train_end": "2026-01-08T00:00:00",
    "purge_start": "2026-01-08T00:00:00",
    "purge_end": "2026-01-08T02:00:00",
    "test_start": "2026-01-08T02:00:00",
    "test_end": "2026-01-15T02:00:00",
    "model_mae": 1.1,
    "model_rmse": 1.2,
    "model_smape": 1.3,
    "model_mase": 1.4,
    "model_da": 0.5,
    "model_f1": 0.6,
    "model_oos_r2": 0.7,
    "naive0_mae": 2.1,
    "naive0_rmse": 2.2,
    "naive0_smape": 2.3,
    "naive0_mase": 2.4,
    "naive0_da": 0.4,
    "naive0_f1": 0.3,
    "naive0_oos_r2": 0.2,
    "client_baseline": None,
    "has_client_model": False,
}


def _split_record(split_index: int, dm_verdict: str) -> dict:
    return {
        "split_index": split_index,
        "dm_statistic": -2.0 if dm_verdict == "better" else 2.0,
        "dm_pvalue": 0.01,
        "dm_verdict": dm_verdict,
        **_BASE_SPLIT_FIELDS,
    }


SPLITS_SUMMARY_BODY = {
    "items": [
        {
            "run_id": RUN_ID_BETTER,
            "splits": [_split_record(0, "better"), _split_record(1, "better")],
        },
        {
            "run_id": RUN_ID_WORSE,
            "splits": [_split_record(0, "worse"), _split_record(1, "worse")],
        },
        {
            "run_id": RUN_ID_MIXED,
            "splits": [_split_record(0, "better"), _split_record(1, "worse")],
        },
        # RUN_ID_ZERO_SPLITS deliberately absent -- `run_splits_summary.get`
        # must default to `[]`, per RAV-012's own documented contract.
    ]
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


def _row_html(response_text: str, run_id: str) -> str:
    start = response_text.index(f'href="/runs/{run_id}"')
    end = response_text.index("</tr>", start)
    return response_text[start:end]


def test_runs_list_renders_correct_verdict_per_row_and_no_results_for_zero_splits(
    monkeypatch,
) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs":
            return httpx.Response(200, json=RUNS_LIST_BODY)
        assert request.url.path == "/runs/splits/summary"
        return httpx.Response(200, json=SPLITS_SUMMARY_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200

    better_row = _row_html(response.text, RUN_ID_BETTER)
    assert 'verdict-badge-better">Beat Naive0 on 2/2 splits</span>' in better_row

    worse_row = _row_html(response.text, RUN_ID_WORSE)
    assert 'verdict-badge-worse">Beat Naive0 on 0/2 splits</span>' in worse_row

    mixed_row = _row_html(response.text, RUN_ID_MIXED)
    assert 'verdict-badge-no-sig-diff">Beat Naive0 on 1/2 splits</span>' in mixed_row

    zero_split_row = _row_html(response.text, RUN_ID_ZERO_SPLITS)
    assert "No results yet" in zero_split_row
    assert "verdict-badge" not in zero_split_row


def test_runs_list_verdict_column_header_present(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/runs":
            return httpx.Response(200, json=RUNS_LIST_BODY)
        return httpx.Response(200, json=SPLITS_SUMMARY_BODY)

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200
    assert "Benchmark comparison" in response.text


def test_runs_list_verdict_indicator_copy_has_no_banned_words() -> None:
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "runs_list.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in ("buy", "sell", "signal", "recommend", "predict", "forecast"):
        assert banned not in text, f"banned word {banned!r} found in runs_list.html"
