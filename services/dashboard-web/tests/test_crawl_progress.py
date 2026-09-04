"""DASH-118: `_format_progress` unit tests plus route-level proof that the
new "Progress" column renders the honest-absence string for a
`blockchain_info_*`-shaped stub (progress fields `null`) and the real row
count for a Binance-shaped stub (progress fields present).

Reuses `tests/test_monitoring.py`'s `httpx.Client`-monkeypatching convention
and tenant-session-cookie login helper -- no new mocking approach.
"""

from __future__ import annotations

from datetime import datetime, timezone

import httpx
import pytest
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app
from app.routers.operator import _format_progress

RAW_KEY = "crawl-progress-test-raw-api-key"

_BANNED_WORDS = ("eta", "estimated completion", "time remaining", "prediction", "forecast")


@pytest.fixture(autouse=True)
def _clear_sessions():
    yield
    get_session_store()._sessions.clear()


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(base_url=base_url, transport=httpx.MockTransport(handler))

    monkeypatch.setattr(httpx, "Client", _fake_client)


# _format_progress direct unit tests


def test_format_progress_none_rows_returns_honest_absence_string() -> None:
    now = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    entry = {"rows_fetched_so_far": None, "updated_at": None}

    assert _format_progress(entry, now) == "no live progress for this source"


def test_format_progress_present_rows_and_recent_updated_at() -> None:
    now = datetime(2026, 1, 2, 0, 0, 3, tzinfo=timezone.utc)
    entry = {
        "rows_fetched_so_far": 143000,
        "updated_at": "2026-01-02T00:00:00+00:00",
    }

    result = _format_progress(entry, now)

    assert "143000" in result
    assert "3s ago" in result


def test_format_progress_present_rows_minutes_ago() -> None:
    now = datetime(2026, 1, 2, 0, 5, 0, tzinfo=timezone.utc)
    entry = {
        "rows_fetched_so_far": 500,
        "updated_at": "2026-01-02T00:00:00+00:00",
    }

    result = _format_progress(entry, now)

    assert "500" in result
    assert "5m ago" in result


def test_format_progress_present_rows_hours_ago() -> None:
    now = datetime(2026, 1, 2, 3, 0, 0, tzinfo=timezone.utc)
    entry = {
        "rows_fetched_so_far": 1000,
        "updated_at": "2026-01-02T00:00:00+00:00",
    }

    result = _format_progress(entry, now)

    assert "1000" in result
    assert "3h ago" in result


def test_format_progress_present_rows_missing_updated_at_degrades_gracefully() -> None:
    now = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    entry = {"rows_fetched_so_far": 250, "updated_at": None}

    result = _format_progress(entry, now)

    assert "250" in result
    assert "ago" not in result


def test_format_progress_present_rows_unparseable_updated_at_degrades_gracefully() -> None:
    now = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    entry = {"rows_fetched_so_far": 250, "updated_at": "not-a-timestamp"}

    result = _format_progress(entry, now)

    assert "250" in result
    assert "ago" not in result


def test_format_progress_present_rows_missing_updated_at_key_entirely() -> None:
    now = datetime(2026, 1, 2, 0, 0, 0, tzinfo=timezone.utc)
    entry = {"rows_fetched_so_far": 42}

    result = _format_progress(entry, now)

    assert "42" in result


def test_format_progress_never_raises_for_naive_vs_aware_mismatch() -> None:
    now = datetime(2026, 1, 2, 0, 0, 0)  # naive
    entry = {
        "rows_fetched_so_far": 10,
        "updated_at": "2026-01-02T00:00:00+00:00",  # aware
    }

    result = _format_progress(entry, now)

    assert "10" in result


@pytest.mark.parametrize(
    "entry",
    [
        {"rows_fetched_so_far": None, "updated_at": None},
        {"rows_fetched_so_far": 143000, "updated_at": "2026-01-02T00:00:00+00:00"},
        {"rows_fetched_so_far": 250, "updated_at": None},
        {"rows_fetched_so_far": 250, "updated_at": "not-a-timestamp"},
    ],
)
def test_format_progress_never_contains_banned_prediction_words(entry) -> None:
    now = datetime(2026, 1, 2, 0, 0, 3, tzinfo=timezone.utc)

    result = _format_progress(entry, now).lower()

    for banned in _BANNED_WORDS:
        assert banned not in result, f"banned word {banned!r} found in {result!r}"


# Route-level: blockchain.info-shaped stub (progress fields null) vs
# Binance-shaped stub (progress fields present)


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


def test_monitoring_shows_honest_absence_for_blockchain_info_source(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path == "/system/health":
            return _health_response()
        if request.url.path == "/ingestion/datasets":
            return httpx.Response(
                200,
                json={
                    "items": [
                        {
                            "source": "blockchain_info_hashrate",
                            "earliest_timestamp": "2026-01-01T00:00:00",
                            "latest_timestamp": "2026-01-02T00:00:00",
                            "row_count": 2,
                        }
                    ]
                },
            )
        if request.url.path == "/ingestion/connectors/blockchain_info_hashrate/status":
            return httpx.Response(
                200,
                json={
                    "status": "running",
                    "timestamp": "2026-01-02T00:00:00",
                    "row_count": None,
                    "rows_fetched_so_far": None,
                    "updated_at": None,
                },
            )
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "no live progress for this source" in response.text


def test_monitoring_shows_row_count_for_binance_source(monkeypatch) -> None:
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
                    "status": "running",
                    "timestamp": "2026-01-02T00:00:00",
                    "row_count": 24,
                    "rows_fetched_so_far": 143000,
                    "updated_at": "2026-01-02T00:00:00+00:00",
                },
            )
        raise AssertionError(f"unexpected request: {request.url.path}")  # pragma: no cover

    _patch_transport(monkeypatch, handler)

    session_id = get_session_store().create(RAW_KEY)
    client = TestClient(app)
    client.cookies.set("session_id", session_id)

    response = client.get("/monitoring")

    assert response.status_code == 200
    assert "143000 rows fetched so far" in response.text
    assert "no live progress for this source" not in response.text


def test_crawl_progress_column_has_no_banned_positioning_words_in_panel_template() -> None:
    template_path = (
        __import__("pathlib").Path(__file__).parent.parent
        / "src"
        / "app"
        / "templates"
        / "_crawl_status_panel.html"
    )
    text = template_path.read_text(encoding="utf-8").lower()

    for banned in _BANNED_WORDS:
        assert banned not in text, f"banned word {banned!r} found in _crawl_status_panel.html"
