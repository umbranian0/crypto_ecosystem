"""DASH-127 (UAT-011): every `data-tooltip` element must carry a matching
`aria-label` (or `aria-describedby` + visually-hidden sibling) with the same
text, so a screen reader announces the tooltip without a mouse hover.

Scans `GET /runs/new`'s rendered HTML (the only template using the
`data-tooltip` pattern as of this ticket -- confirmed via grep across
`src/app/templates/`, see `services/dashboard-web/README.md`'s "Tooltip
accessibility convention (DASH-127)" section) and asserts every
`data-tooltip="..."` span also has `aria-label="..."` with matching text.
"""

from __future__ import annotations

import re

import httpx
from fastapi.testclient import TestClient

from app.dependencies.session import get_session_store
from app.main import app

RAW_KEY = "super-secret-raw-api-key-do-not-leak"

# Matches `data-tooltip="..."`/`data-tooltip='...'` and the immediately
# following `aria-label="..."`/`aria-label='...'` on the same element --
# both attributes are written on the same `<span>` in `run_new.html`
# (`aria-label` always directly follows `data-tooltip`), so a non-greedy
# match across the two is enough without a full HTML parser.
_TOOLTIP_PAIR_RE = re.compile(
    r"""data-tooltip=(?P<dq>["'])(?P<tooltip>.*?)(?P=dq)\s+"""
    r"""aria-label=(?P<aq>["'])(?P<label>.*?)(?P=aq)""",
    re.DOTALL,
)
_BARE_DATA_TOOLTIP_RE = re.compile(r"""data-tooltip=(["']).*?\1""", re.DOTALL)


def _login(client: TestClient) -> None:
    session_store = get_session_store()
    session_id = session_store.create(RAW_KEY)
    client.cookies.set("session_id", session_id)


def _patch_transport(monkeypatch, handler) -> None:
    real_client_cls = httpx.Client

    def _fake_client(*, base_url="", **kwargs):
        return real_client_cls(
            base_url=base_url, transport=httpx.MockTransport(handler)
        )

    monkeypatch.setattr(httpx, "Client", _fake_client)


def test_run_new_every_data_tooltip_has_matching_aria_label(monkeypatch) -> None:
    def handler(request: httpx.Request) -> httpx.Response:
        assert request.url.path == "/ingestion/datasets"
        return httpx.Response(200, json={"items": []})

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")
    assert response.status_code == 200
    html = response.text

    all_tooltips = _BARE_DATA_TOOLTIP_RE.findall(html)
    assert len(all_tooltips) > 0, "expected at least one data-tooltip element"

    paired = _TOOLTIP_PAIR_RE.findall(html)
    assert len(paired) == len(_BARE_DATA_TOOLTIP_RE.findall(html)), (
        "every data-tooltip element must have a matching aria-label on the "
        "same element -- found a data-tooltip with no paired aria-label"
    )

    for _dq, tooltip_text, _aq, label_text in paired:
        assert tooltip_text == label_text, (
            f"aria-label text does not match data-tooltip text: "
            f"{tooltip_text!r} != {label_text!r}"
        )


def test_run_new_dataset_reference_field_tooltip_has_matching_aria_label(
    monkeypatch,
) -> None:
    """AC3: the raw-levels-vs-returns `dataset_reference_field` tooltip
    specifically, called out by name in UAT-011's rationale.
    """

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(
            200,
            json={
                "items": [
                    {
                        "source": "binance_price_btcusdt_1h",
                        "row_count": 100,
                        "earliest_timestamp": "2024-01-01T00:00:00+00:00",
                        "latest_timestamp": "2024-01-05T00:00:00+00:00",
                    }
                ]
            },
        )

    _patch_transport(monkeypatch, handler)

    client = TestClient(app)
    _login(client)

    response = client.get("/runs/new")
    html = response.text

    assert 'id="dataset_reference_field"' in html
    field_block = html.split('id="dataset_reference_field"')[0].rsplit(
        '<label for="dataset_reference_field">', 1
    )[1]
    assert "raw levels" in field_block
    assert "data-tooltip=" in field_block
    assert "aria-label=" in field_block

    match = _TOOLTIP_PAIR_RE.search(field_block)
    assert match is not None
    assert match.group("tooltip") == match.group("label")
    assert "raw levels" in match.group("tooltip")
