"""RPT-002-02: `consistency_trend` report kind (renderer, Factory, generation, endpoint)."""

from __future__ import annotations

from markupsafe import escape
from pathlib import Path

import httpx
import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from naive_first_common.consistency import compute_consistency_indicator
from naive_first_common.contracts import RunSummaryResponse, SplitResultResponse
from naive_first_common.disclosures import NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE

from app.dependencies.http_client import get_validation_service_client
from app.dependencies.repositories import get_report_repository
from app.generation import (
    MAX_RENDERED_SPLITS,
    DownstreamResponseError,
    generate_consistency_trend_report,
)
from app.renderers.consistency_trend import ConsistencyTrendRenderer
from app.renderers.factory import UnknownReportKindError, get_report_renderer
from app.renderers.jinja_env import env
from app.renderers.validation_audit import ValidationAuditRenderer
from app.routers import report_generation
from tests.test_generate_endpoint import FakeReportRepository

TENANT = "tenant-a"
_METRICS = ("mae", "rmse", "smape", "mase", "da", "f1", "oos_r2")


def _split_dict(verdict: str, undefined: bool = False, index: int = 0) -> dict:
    return {
        "split_index": index,
        "train_start": "2026-01-01T00:00:00",
        "train_end": "2026-01-08T00:00:00",
        "purge_start": "2026-01-08T00:00:00",
        "purge_end": "2026-01-08T02:00:00",
        "test_start": "2026-01-08T02:00:00",
        "test_end": "2026-01-15T02:00:00",
        **{f"model_{m}": 1.0 for m in _METRICS},
        **{f"naive0_{m}": 1.0 for m in _METRICS},
        "dm_statistic": None if undefined else 1.0,
        "dm_pvalue": None if undefined else 0.5,
        "dm_verdict": verdict,
    }


def _split(verdict: str, undefined: bool = False, index: int = 0) -> SplitResultResponse:
    return SplitResultResponse(**_split_dict(verdict, undefined, index))


def _run_dict(run_id: str, dataset_id="ds-1", horizon=24, status="completed") -> dict:
    return {
        "id": run_id,
        "dataset_id": dataset_id,
        "horizon": horizon,
        "status": status,
        "created_at": "2026-01-01T00:00:00",
        "completed_at": "2026-01-01T00:05:00" if status == "completed" else None,
    }


def _run(run_id: str, **kw) -> RunSummaryResponse:
    return RunSummaryResponse(**_run_dict(run_id, **kw))


FIXTURE = [
    (_run("run-win"), [_split("better"), _split("better"), _split("worse")]),
    (_run("run-lose"), [_split("worse"), _split("no significant difference")]),
    (_run("run-undef"), [_split("worse", undefined=True)]),
]


def test_factory_dispatch():
    assert isinstance(get_report_renderer("consistency_trend"), ConsistencyTrendRenderer)
    assert isinstance(get_report_renderer("validation_audit"), ValidationAuditRenderer)
    with pytest.raises(UnknownReportKindError):
        get_report_renderer("nope")


def test_renderer_headline_rows_and_undefined_excluded():
    html = ConsistencyTrendRenderer().render("ds-1", 24, FIXTURE)
    assert "Beat Naive0 in 1 of 2 completed runs." in html
    assert "run-win" in html and "run-lose" in html and "run-undef" in html
    assert "not evaluable" in html
    assert str(escape(NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE)) not in html


def test_renderer_parity_with_shared_rule():
    indicator = compute_consistency_indicator(FIXTURE)
    html = ConsistencyTrendRenderer().render("ds-1", 24, FIXTURE)
    assert (
        f"Beat Naive0 in {indicator.beat_count} of {indicator.total_count} completed runs."
        in html
    )


def test_renderer_no_data_state_never_zero_of_zero():
    for runs in ([], [(_run("r"), [_split("x", undefined=True)])]):
        html = ConsistencyTrendRenderer().render("ds-1", 24, runs)
        assert "No completed runs matched this selection." in html
        assert "0 of 0" not in html
        assert str(escape(NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE)) not in html


def test_renderer_appends_expected_sentence_when_none_beat():
    html = ConsistencyTrendRenderer().render("ds-1", 24, [(_run("r"), [_split("worse")])])
    assert "Beat Naive0 in 0 of 1 completed runs." in html
    assert str(escape(NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE)) in html


def test_renderer_escapes_dataset_id():
    html = ConsistencyTrendRenderer().render("<script>alert(1)</script>", 24, [])
    assert "<script>alert(1)</script>" not in html
    assert "&lt;script&gt;" in html


def test_renderer_includes_shared_disclaimer():
    html = ConsistencyTrendRenderer().render("ds-1", 24, FIXTURE)
    assert "This audit evaluates statistical forecast accuracy only." in html


def test_renderer_copy_has_no_banned_positioning_words():
    # The shared disclaimer legitimately says "unprofitable"/"forecast"; scan the rest.
    disclaimer = env.get_template("_accuracy_vs_economic_disclaimer.html.jinja").render()
    html = ConsistencyTrendRenderer().render("ds-1", 24, FIXTURE).replace(disclaimer, "").lower()
    for banned in ("predict", "signal", "profit", "improve", "alpha"):
        assert banned not in html, banned


def test_reporting_service_has_no_copy_of_the_rule():
    src = Path(__file__).resolve().parent.parent / "src"
    for path in src.rglob("*.py"):
        text = path.read_text(encoding="utf-8")
        assert "def run_beats_naive0" not in text
        assert "def compute_consistency_indicator" not in text
        assert "def verdict_category" not in text


class FakeValidation:
    def __init__(self, runs: list[dict], splits: dict[str, list[dict]]):
        self.runs = runs
        self.splits = splits
        self.requests: list[httpx.Request] = []
        self.fail_status: int | None = None

    def handler(self, request: httpx.Request) -> httpx.Response:
        self.requests.append(request)
        if self.fail_status:
            return httpx.Response(self.fail_status, json={})
        path = request.url.path
        if path == "/runs":
            limit = int(request.url.params["limit"])
            offset = int(request.url.params["offset"])
            return httpx.Response(
                200,
                json={
                    "items": self.runs[offset : offset + limit],
                    "limit": limit,
                    "offset": offset,
                    "total": len(self.runs),
                },
            )
        run_id = path.split("/")[2]
        if path.endswith("/splits/count"):
            return httpx.Response(200, json={"total": len(self.splits[run_id])})
        limit = int(request.url.params["limit"])
        offset = int(request.url.params["offset"])
        return httpx.Response(200, json=self.splits[run_id][offset : offset + limit])


def _client(fake: FakeValidation) -> httpx.Client:
    return httpx.Client(transport=httpx.MockTransport(fake.handler), base_url="http://vs")


def test_generation_pages_filters_and_persists_scope_key():
    runs = [_run_dict(f"r{i}") for i in range(130)]
    runs += [
        _run_dict("other-ds", dataset_id="ds-2"),
        _run_dict("other-h", horizon=6),
        _run_dict("failed", status="failed"),
    ]
    splits = {r["id"]: [_split_dict("better")] for r in runs}
    fake = FakeValidation(runs, splits)
    repo = FakeReportRepository()

    record = generate_consistency_trend_report(TENANT, "ds-1", 24, _client(fake), repo)

    assert record.run_id == "consistency_trend:ds-1:24"
    assert repo.created[0].report_kind == "consistency_trend"
    assert "Beat Naive0 in 130 of 130 completed runs." in repo.created[0].content
    assert sum(1 for r in fake.requests if r.url.path == "/runs") == 2
    assert all(r.headers["x-tenant-id"] == TENANT for r in fake.requests)
    fetched = {r.url.path.split("/")[2] for r in fake.requests if r.url.path != "/runs"}
    assert fetched == {f"r{i}" for i in range(130)}


def test_generation_bounds_splits_to_most_recent_cap():
    older = [_split_dict("worse", index=i) for i in range(10)]
    recent = [_split_dict("better", index=10 + i) for i in range(MAX_RENDERED_SPLITS)]
    fake = FakeValidation([_run_dict("r0")], {"r0": older + recent})
    repo = FakeReportRepository()
    generate_consistency_trend_report(TENANT, "ds-1", 24, _client(fake), repo)
    page = [r for r in fake.requests if r.url.path == "/runs/r0/splits"][0]
    assert page.url.params["offset"] == "10"
    assert page.url.params["limit"] == str(MAX_RENDERED_SPLITS)
    assert "Beat Naive0 in 1 of 1 completed runs." in repo.created[0].content


def test_generation_empty_group_persists_no_data_report():
    fake = FakeValidation([_run_dict("r0", dataset_id="ds-2")], {"r0": []})
    repo = FakeReportRepository()
    generate_consistency_trend_report(TENANT, "ds-1", 24, _client(fake), repo)
    assert "No completed runs matched this selection." in repo.created[0].content


def test_generation_downstream_non_2xx_raises():
    fake = FakeValidation([], {})
    fake.fail_status = 500
    with pytest.raises(DownstreamResponseError):
        generate_consistency_trend_report(TENANT, "ds-1", 24, _client(fake), FakeReportRepository())


@pytest.fixture()
def endpoint():
    fake = FakeValidation([_run_dict("r0")], {"r0": [_split_dict("better"), _split_dict("better")]})
    repo = FakeReportRepository()
    app = FastAPI()
    app.include_router(report_generation.router, prefix="/reports")
    app.dependency_overrides[get_validation_service_client] = lambda: _client(fake)
    app.dependency_overrides[get_report_repository] = lambda: repo
    return TestClient(app), fake, repo


def test_endpoint_generates_trend_report(endpoint):
    client, fake, repo = endpoint
    response = client.post(
        "/reports/generate",
        json={"kind": "consistency_trend", "dataset_id": "ds-1", "horizon": 24},
        headers={"X-Tenant-Id": TENANT},
    )
    assert response.status_code == 201
    assert response.json() == {"id": "report-0", "status": "generated"}
    assert repo.created[0].tenant_id == TENANT
    assert all(r.headers["x-tenant-id"] == TENANT for r in fake.requests)


@pytest.mark.parametrize(
    "body",
    [
        {"kind": "consistency_trend", "dataset_id": "ds-1"},
        {"kind": "consistency_trend", "horizon": 24},
        {"kind": "consistency_trend", "dataset_id": "ds-1", "horizon": 24, "run_id": "r0"},
        {"kind": "validation_audit"},
        {"run_id": "r0", "dataset_id": "ds-1"},
        {"run_id": "r0", "horizon": 24},
        {"kind": "bogus", "run_id": "r0"},
        {},
    ],
)
def test_endpoint_rejects_invalid_combinations(endpoint, body):
    client, _fake, repo = endpoint
    response = client.post("/reports/generate", json=body, headers={"X-Tenant-Id": TENANT})
    assert response.status_code == 422
    assert repo.created == []


def test_endpoint_maps_downstream_error_as_before(endpoint):
    client, fake, _repo = endpoint
    fake.fail_status = 500
    response = client.post(
        "/reports/generate",
        json={"kind": "consistency_trend", "dataset_id": "ds-1", "horizon": 24},
        headers={"X-Tenant-Id": TENANT},
    )
    assert response.status_code == 502
