"""AI-002 tests: `app.narrative.generation.generate_narrative_html`, using a
`FakeNarrativeClient` test double implementing `NarrativeClient` (ticket Test
acceptance criteria) -- no real model call anywhere in this suite.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone

from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

from app.narrative.client import NarrativeClientError
from app.narrative.generation import generate_narrative_html


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


def _make_run() -> RunDetailResponse:
    return RunDetailResponse(
        id="run-1",
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=24,
        purge_gap_hours=24,
        split_config={},
        status="completed",
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=datetime(2026, 1, 2, tzinfo=timezone.utc),
        failure_reason=None,
    )


def _make_split(dm_verdict: str) -> SplitResultResponse:
    return SplitResultResponse(
        split_index=0,
        train_start=datetime(2026, 1, 1, tzinfo=timezone.utc),
        train_end=datetime(2026, 1, 5, tzinfo=timezone.utc),
        purge_start=datetime(2026, 1, 5, tzinfo=timezone.utc),
        purge_end=datetime(2026, 1, 6, tzinfo=timezone.utc),
        test_start=datetime(2026, 1, 6, tzinfo=timezone.utc),
        test_end=datetime(2026, 1, 7, tzinfo=timezone.utc),
        model_mae=0.1,
        model_rmse=0.2,
        model_smape=0.3,
        model_mase=0.4,
        model_da=0.5,
        model_f1=0.6,
        model_oos_r2=-0.1,
        naive0_mae=0.11,
        naive0_rmse=0.21,
        naive0_smape=0.31,
        naive0_mase=0.41,
        naive0_da=0.51,
        naive0_f1=0.61,
        naive0_oos_r2=0.01,
        dm_statistic=-3.1,
        dm_pvalue=0.01,
        dm_verdict=dm_verdict,
    )


def test_success_path_returns_generated_text():
    run = _make_run()
    splits = [_make_split("worse")]
    client = FakeNarrativeClient(responses=["The model did not beat naive on the split evaluated."])

    result = generate_narrative_html(run, splits, client)

    assert result == "The model did not beat naive on the split evaluated."
    assert client.calls == 1


def test_fact_check_failure_regenerates_then_falls_back_to_none():
    run = _make_run()
    splits = [_make_split("worse")]
    # First attempt: directionally-wrong claim. Second attempt: still wrong
    # -- proves the caller never receives the false claim, falls back to
    # None ("narrative unavailable") rather than shipping either attempt.
    client = FakeNarrativeClient(
        responses=[
            "The model beat naive on the split evaluated.",
            "The model beat naive on the split evaluated, again.",
        ]
    )

    result = generate_narrative_html(run, splits, client)

    assert result is None
    assert client.calls == 2


def test_fact_check_failure_then_success_on_regenerate_ships_corrected_version():
    run = _make_run()
    splits = [_make_split("worse")]
    client = FakeNarrativeClient(
        responses=[
            "The model beat naive on the split evaluated.",
            "The model did not beat naive on the split evaluated.",
        ]
    )

    result = generate_narrative_html(run, splits, client)

    assert result == "The model did not beat naive on the split evaluated."
    assert client.calls == 2


def test_banned_term_response_falls_back_to_none():
    run = _make_run()
    splits = [_make_split("worse")]
    client = FakeNarrativeClient(
        responses=["You should buy based on this.", "You should sell based on this."]
    )

    result = generate_narrative_html(run, splits, client)

    assert result is None


def test_client_error_falls_back_to_none():
    run = _make_run()
    splits = [_make_split("worse")]
    client = FakeNarrativeClient(
        responses=[NarrativeClientError("timeout"), NarrativeClientError("timeout again")]
    )

    result = generate_narrative_html(run, splits, client)

    assert result is None
    assert client.calls == 2


def test_client_error_then_success_on_retry_ships_generated_text():
    run = _make_run()
    splits = [_make_split("worse")]
    client = FakeNarrativeClient(
        responses=[
            NarrativeClientError("timeout"),
            "The model did not beat naive on the split evaluated.",
        ]
    )

    result = generate_narrative_html(run, splits, client)

    assert result == "The model did not beat naive on the split evaluated."
