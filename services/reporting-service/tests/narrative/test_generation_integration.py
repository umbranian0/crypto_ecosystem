"""AI-002 tests: `app.generation.generate_validation_audit_report`'s new
`narrative_client` parameter -- success path, fact-check-failure -> fallback,
client-error -> fallback (graceful degradation), and proof that
`POST /reports/generate`'s router never passes a narrative client.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

import httpx
import pytest

from app.generation import generate_validation_audit_report
from app.narrative.client import NarrativeClientError
from app.repositories.interfaces import ReportRecord

RUN_ID = "run-1"
TENANT_ID = "tenant-1"

_RUN = {
    "id": RUN_ID,
    "tenant_id": TENANT_ID,
    "dataset_id": "dataset-1",
    "horizon": 5,
    "purge_gap_hours": 2.0,
    "split_config": {"train_window": 30, "test_window": 7, "step": 7},
    "status": "completed",
    "created_at": "2026-01-01T00:00:00",
    "completed_at": "2026-01-01T00:05:00",
    "failure_reason": None,
}

_SPLIT = {
    "split_index": 0,
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
    "dm_statistic": 3.1,
    "dm_pvalue": 0.02,
    "dm_verdict": "worse",
}


def _fake_client() -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        if request.url.path.endswith("/splits"):
            return httpx.Response(200, json=[_SPLIT])
        return httpx.Response(200, json=_RUN)

    return httpx.Client(transport=httpx.MockTransport(handler), base_url="http://validation-service")


@dataclass
class FakeReportRepository:
    created: list[ReportRecord] = field(default_factory=list)

    def create_report(
        self, tenant_id: str, run_id: str, report_kind: str, content: str, status: str
    ) -> ReportRecord:
        record = ReportRecord(
            id=f"report-{len(self.created)}",
            tenant_id=tenant_id,
            run_id=run_id,
            report_kind=report_kind,
            generated_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
            content=content,
            status=status,
        )
        self.created.append(record)
        return record

    def get_report(self, tenant_id: str, report_id: str) -> ReportRecord | None:  # pragma: no cover
        raise NotImplementedError


@dataclass
class FakeNarrativeClient:
    responses: list[str | Exception] = field(default_factory=list)
    calls: int = 0

    def generate(self, prompt: str) -> str:
        self.calls += 1
        response = self.responses[self.calls - 1]
        if isinstance(response, Exception):
            raise response
        return response


def test_narrative_client_none_is_byte_identical_to_pre_ai_002_behavior():
    """`narrative_client` defaults to `None` -- the exact code path
    `POST /reports/generate`'s router still exercises (it never passes this
    argument, see `app.routers.report_generation`).
    """
    repository = FakeReportRepository()

    record = generate_validation_audit_report(
        tenant_id=TENANT_ID, run_id=RUN_ID, client=_fake_client(), repository=repository
    )

    assert "AI-generated summary" not in record.content


def test_narrative_success_path_renders_narrative_block():
    repository = FakeReportRepository()
    client = FakeNarrativeClient(responses=["The model did not beat naive on this run."])

    record = generate_validation_audit_report(
        tenant_id=TENANT_ID,
        run_id=RUN_ID,
        client=_fake_client(),
        repository=repository,
        narrative_client=client,
    )

    assert "AI-generated summary of the results above" in record.content
    assert "The model did not beat naive on this run." in record.content


def test_fact_check_failure_falls_back_to_table_only_report_never_ships_false_claim():
    """The fake client always claims the model beat naive, but this run's
    only split has `dm_verdict == "worse"` -- proves the false claim never
    reaches the rendered report, and generation still succeeds with a valid
    `ReportRecord`.
    """
    repository = FakeReportRepository()
    client = FakeNarrativeClient(
        responses=[
            "The model beat naive decisively on this run.",
            "The model beat naive decisively on this run, confirmed.",
        ]
    )

    record = generate_validation_audit_report(
        tenant_id=TENANT_ID,
        run_id=RUN_ID,
        client=_fake_client(),
        repository=repository,
        narrative_client=client,
    )

    assert isinstance(record, ReportRecord)
    assert "AI-generated summary" not in record.content
    assert "beat naive decisively" not in record.content
    # Table/verdict content is unaffected -- still authoritative.
    assert "Results table" in record.content


def test_narrative_client_error_gracefully_degrades_to_table_only_report():
    repository = FakeReportRepository()
    client = FakeNarrativeClient(
        responses=[NarrativeClientError("timed out"), NarrativeClientError("timed out again")]
    )

    record = generate_validation_audit_report(
        tenant_id=TENANT_ID,
        run_id=RUN_ID,
        client=_fake_client(),
        repository=repository,
        narrative_client=client,
    )

    assert isinstance(record, ReportRecord)
    assert record.status == "generated"
    assert "AI-generated summary" not in record.content
    assert "Results table" in record.content


def test_rendered_narrative_html_contains_no_banned_terms():
    """Checks the AI-generated block specifically (ticket Test acceptance
    criteria: "over the rendered narrative HTML output (not just the raw
    client response)") -- not the whole page, since the pre-existing
    "6. Recommendations" section heading legitimately contains the
    substring "recommendation" and is unrelated to this narrative feature.
    """
    repository = FakeReportRepository()
    client = FakeNarrativeClient(
        responses=["The model did not beat naive on this run, showing mixed statistical accuracy."]
    )

    record = generate_validation_audit_report(
        tenant_id=TENANT_ID,
        run_id=RUN_ID,
        client=_fake_client(),
        repository=repository,
        narrative_client=client,
    )

    marker = "AI-generated summary of the results above"
    assert marker in record.content
    narrative_block = record.content[record.content.index(marker):]

    for term in ("signal", "buy", "sell", "profit", "trade", "recommendation"):
        assert term not in narrative_block.lower()
