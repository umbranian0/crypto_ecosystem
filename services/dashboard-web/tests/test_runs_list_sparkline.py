"""RAV-014: `runs_list.html`'s new per-run error sparkline column.

The sprint's own required test: a fixture run with >= 2 splits renders a
sparkline with the correct bar count; a zero/one-split run renders the
placeholder state instead, never a broken/misleadingly flat SVG. Reuses the
same `_patch_transport`-style `httpx.Client` monkeypatch as
`test_runs_list_verdict_indicator.py`/`test_runs_list.py` (this router builds
`httpx.Client(base_url=...)` per-request rather than depending on an
injectable client).
"""

from __future__ import annotations

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"

RUN_ID_MULTI_SPLIT = "11111111-1111-1111-1111-111111111111"
RUN_ID_ONE_SPLIT = "22222222-2222-2222-2222-222222222222"
RUN_ID_ZERO_SPLITS = "33333333-3333-3333-3333-333333333333"

RUNS_LIST_BODY = {
    "items": [
        {
            "id": RUN_ID_MULTI_SPLIT,
            "dataset_id": "dataset-1",
            "horizon": 24,
            "status": "completed",
            "created_at": "2026-08-04T00:00:00Z",
            "completed_at": "2026-08-04T01:00:00Z",
        },
        {
            "id": RUN_ID_ONE_SPLIT,
            "dataset_id": "dataset-2",
            "horizon": 6,
            "status": "completed",
            "created_at": "2026-08-03T00:00:00Z",
            "completed_at": "2026-08-03T01:00:00Z",
        },
        {
            "id": RUN_ID_ZERO_SPLITS,
            "dataset_id": "dataset-3",
            "horizon": 1,
            "status": "running",
            "created_at": "2026-08-01T00:00:00Z",
            "completed_at": None,
        },
    ],
    "limit": 50,
    "offset": 0,
    "total": 3,
}

_BASE_SPLIT_FIELDS = {
    "train_start": "2026-01-01T00:00:00",
    "train_end": "2026-01-08T00:00:00",
    "purge_start": "2026-01-08T00:00:00",
    "purge_end": "2026-01-08T02:00:00",
    "test_start": "2026-01-08T02:00:00",
    "test_end": "2026-01-15T02:00:00",
    "model_rmse": 1.2,
    "model_smape": 1.3,
    "model_mase": 1.4,
    "model_da": 0.5,
    "model_f1": 0.6,
    "model_oos_r2": 0.7,
    "naive0_rmse": 2.2,
    "naive0_smape": 2.3,
    "naive0_mase": 2.4,
    "naive0_da": 0.4,
    "naive0_f1": 0.3,
    "naive0_oos_r2": 0.2,
    "client_baseline": None,
    "has_client_model": False,
    "dm_statistic": -2.0,
    "dm_pvalue": 0.01,
    "dm_verdict": "better",
}


def _split_record(split_index: int, model_mae: float, naive0_mae: float) -> dict:
    return {
        "split_index": split_index,
        "model_mae": model_mae,
        "naive0_mae": naive0_mae,
        **_BASE_SPLIT_FIELDS,
    }


SPLITS_SUMMARY_BODY = {
    "items": [
        {
            "run_id": RUN_ID_MULTI_SPLIT,
            "splits": [
                _split_record(0, model_mae=1.0, naive0_mae=2.0),
                _split_record(1, model_mae=4.0, naive0_mae=2.0),
                _split_record(2, model_mae=0.5, naive0_mae=1.5),
            ],
        },
        {
            "run_id": RUN_ID_ONE_SPLIT,
            "splits": [_split_record(0, model_mae=1.0, naive0_mae=2.0)],
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


def _handler(request: httpx.Request) -> httpx.Response:
    if request.url.path == "/runs":
        return httpx.Response(200, json=RUNS_LIST_BODY)
    assert request.url.path == "/runs/splits/summary"
    return httpx.Response(200, json=SPLITS_SUMMARY_BODY)


def test_runs_list_renders_sparkline_with_correct_bar_count(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200

    multi_split_row = _row_html(response.text, RUN_ID_MULTI_SPLIT)
    assert 'class="sparkline-svg"' in multi_split_row
    assert multi_split_row.count('class="bar-model"') == 3
    assert multi_split_row.count('class="bar-naive0"') == 3
    assert "sparkline-placeholder" not in multi_split_row


def test_runs_list_renders_placeholder_for_one_split_run(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200

    one_split_row = _row_html(response.text, RUN_ID_ONE_SPLIT)
    assert '<span class="sparkline-placeholder">Not enough splits yet</span>' in one_split_row
    assert 'class="sparkline-svg"' not in one_split_row


def test_runs_list_renders_placeholder_for_zero_split_run(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200

    zero_split_row = _row_html(response.text, RUN_ID_ZERO_SPLITS)
    assert '<span class="sparkline-placeholder">Not enough splits yet</span>' in zero_split_row
    assert 'class="sparkline-svg"' not in zero_split_row


def test_runs_list_sparkline_column_header_present(monkeypatch) -> None:
    _patch_transport(monkeypatch, _handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs")

    assert response.status_code == 200
    assert "Error by split (MAE)" in response.text


def test_runs_list_sparkline_copy_has_no_banned_words() -> None:
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
