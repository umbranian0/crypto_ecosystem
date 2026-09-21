"""RS-003 tests: `ReportRenderer`/`get_report_renderer` Factory and
`ValidationAuditRenderer`.

Extra-scrutiny checks (ticket RS-003 Test acceptance criteria): the mandatory
statistical-accuracy-vs-economic-value disclaimer must be present verbatim in
every rendered report (completed/mixed, all-worse, and status-only), a
did-not-beat-naive outcome must render plainly, and the Factory must raise a
typed error for an unknown report kind rather than fail silently.
"""

from __future__ import annotations

from datetime import datetime, timezone

import pytest
from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

from app.renderers.factory import UnknownReportKindError, get_report_renderer
from naive_first_common.disclosures import METHODOLOGY_FACTS as shared_methodology_facts

from app.renderers.validation_audit import METHODOLOGY_FACTS, ValidationAuditRenderer

DISCLAIMER_TEXT = (
    "This audit evaluates statistical forecast accuracy only. No transaction costs, "
    "slippage, execution, or position sizing were modeled unless the client separately "
    "commissioned the economic module (Subsystem 5). A model that beats naive statistically "
    "may still be unprofitable after costs, and vice versa is not implied either."
)


def _make_run(
    status: str = "completed",
    failure_reason: str | None = None,
    engine_version: str | None = None,
    config_fingerprint: str | None = None,
) -> RunDetailResponse:
    return RunDetailResponse(
        id="run-1",
        tenant_id="tenant-1",
        dataset_id="dataset-1",
        horizon=24,
        purge_gap_hours=24,
        split_config={},
        status=status,
        created_at=datetime(2026, 1, 1, tzinfo=timezone.utc),
        completed_at=(
            datetime(2026, 1, 2, tzinfo=timezone.utc) if status == "completed" else None
        ),
        failure_reason=failure_reason,
        engine_version=engine_version,
        config_fingerprint=config_fingerprint,
    )


def _make_split(index: int, dm_verdict: str, dm_statistic: float, dm_pvalue: float) -> SplitResultResponse:
    return SplitResultResponse(
        split_index=index,
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
        dm_statistic=dm_statistic,
        dm_pvalue=dm_pvalue,
        dm_verdict=dm_verdict,
    )


def test_get_report_renderer_returns_validation_audit_renderer():
    renderer = get_report_renderer("validation_audit")
    assert isinstance(renderer, ValidationAuditRenderer)


def test_get_report_renderer_raises_typed_error_for_unknown_kind():
    with pytest.raises(UnknownReportKindError):
        get_report_renderer("nonexistent_kind")


def test_completed_run_with_mixed_verdicts_renders_table_verdict_and_disclaimer():
    run = _make_run(status="completed")
    splits = [
        _make_split(0, "better", -3.1, 0.01),
        _make_split(1, "worse", 2.8, 0.02),
        _make_split(2, "no significant difference", 0.5, 0.6),
    ]

    html = ValidationAuditRenderer().render(run, splits)

    assert "run-1" in html
    assert "Results table" in html
    assert "dataset-1" in html
    # DM fields rendered verbatim, unmodified.
    assert "-3.1" in html
    assert "2.8" in html
    assert "0.01" in html
    assert "better" in html
    assert "worse" in html
    assert "no significant difference" in html
    assert "mixed across splits" in html
    assert DISCLAIMER_TEXT in html


def test_run_that_never_beats_naive_renders_did_not_beat_naive_plainly():
    run = _make_run(status="completed")
    splits = [
        _make_split(0, "worse", 2.8, 0.02),
        _make_split(1, "worse", 3.1, 0.01),
    ]

    html = ValidationAuditRenderer().render(run, splits)

    assert "did not beat naive" in html
    assert "0 better, 2 worse" in html
    assert DISCLAIMER_TEXT in html


def test_failed_run_with_no_splits_renders_status_only_report_without_error():
    run = _make_run(status="failed", failure_reason="dataset unreachable")

    html = ValidationAuditRenderer().render(run, [])

    assert "failed" in html
    assert "dataset unreachable" in html
    assert "has not completed" in html
    assert "Results table" not in html
    assert DISCLAIMER_TEXT in html


def test_running_run_with_no_splits_renders_status_only_report():
    run = _make_run(status="running")

    html = ValidationAuditRenderer().render(run, [])

    assert "running" in html
    assert "has not completed" in html
    assert DISCLAIMER_TEXT in html


def test_narrative_html_none_renders_byte_identical_output_to_no_narrative_call(tmp_path):
    """AI-002 Test acceptance criteria: `narrative_html=None` (the default)
    must produce byte-identical output to calling `render` without that
    keyword at all -- proves adding the optional parameter didn't change
    today's table-only output for any existing caller.
    """
    run = _make_run(status="completed")
    splits = [_make_split(0, "better", -3.1, 0.01)]

    html_without_kwarg = ValidationAuditRenderer().render(run, splits)
    html_with_none = ValidationAuditRenderer().render(run, splits, narrative_html=None)

    assert html_without_kwarg == html_with_none
    assert "AI-generated summary" not in html_without_kwarg


def test_narrative_html_present_renders_labeled_block():
    run = _make_run(status="completed")
    splits = [_make_split(0, "better", -3.1, 0.01)]

    html = ValidationAuditRenderer().render(
        run, splits, narrative_html="This is the AI narrative paragraph text."
    )

    assert "AI-generated summary of the results above" in html
    assert "This is the AI narrative paragraph text." in html


def test_fingerprinted_run_renders_reproducibility_statement_facts():
    """TRUST-004: a run with both `engine_version`/`config_fingerprint` set
    (the post-TRUST-003 contract) renders all four required facts: engine
    version, config fingerprint, dataset reference, and the fixed
    reproducibility-expectation sentence.
    """
    run = _make_run(
        status="completed",
        engine_version="naive_first_engine==1.4.0",
        config_fingerprint="a3f5c9...deadbeef",
    )
    splits = [_make_split(0, "better", -3.1, 0.01)]

    html = ValidationAuditRenderer().render(run, splits)

    assert "Reproducibility statement" in html
    assert "naive_first_engine==1.4.0" in html
    assert "a3f5c9...deadbeef" in html
    assert "dataset-1" in html
    assert "expected to reproduce these results" in html


def test_null_fingerprint_run_renders_not_available_note_without_leaking_none():
    """TRUST-004: a pre-TRUST-003 run (`engine_version`/`config_fingerprint`
    both `None`, `_make_run`'s existing default) renders the explicit
    not-available note and never leaks Jinja2's `None -> "None"` string
    coercion into the subsection.
    """
    run = _make_run(status="completed")
    splits = [_make_split(0, "better", -3.1, 0.01)]

    html = ValidationAuditRenderer().render(run, splits)
    normalized_html = " ".join(html.split())

    assert (
        "not available for runs created before this platform tracked "
        "engine fingerprints" in normalized_html
    )

    start = html.index("Reproducibility statement")
    end = html.index("3. Results table (per split)")
    subsection = html[start:end]
    assert "None" not in subsection


def test_reproducibility_statement_sits_between_leakage_params_and_results_table():
    """TRUST-004 placement acceptance criterion: the new subsection's heading
    appears strictly after "leakage-protocol parameter values" and strictly
    before "Results table (per split)" in the rendered HTML.
    """
    run = _make_run(status="completed")
    splits = [_make_split(0, "better", -3.1, 0.01)]

    html = ValidationAuditRenderer().render(run, splits)

    assert html.index("leakage-protocol parameter values") < html.index("Reproducibility statement")
    assert html.index("Reproducibility statement") < html.index("Results table (per split)")


def test_non_completed_run_omits_reproducibility_statement():
    """The new subsection lives inside the existing `else` branch of the
    `run.status != "completed"` guard, so a non-completed run must omit it
    entirely, same as every other results-dependent section.
    """
    run = _make_run(status="running")

    html = ValidationAuditRenderer().render(run, [])

    assert "Reproducibility statement" not in html


def test_methodology_section_renders_for_non_completed_zero_split_run():
    """TRUST-001-02: the new "2. Methodology" section is always-visible --
    it must render, with all four facts verbatim, even for a run that has
    not completed and has zero splits. This is the regression-proof test for
    the gap this ticket closes."""
    import html as html_module

    run = _make_run(status="running")

    rendered = html_module.unescape(ValidationAuditRenderer().render(run, []))

    assert "2. Methodology" in rendered
    for fact in METHODOLOGY_FACTS:
        assert fact in rendered


def test_methodology_section_renders_for_completed_multi_split_run():
    """Same assertion repeated for a "completed", multi-split run -- the
    section is present regardless of status, not only for the non-completed
    case."""
    import html as html_module

    run = _make_run(status="completed")
    splits = [
        _make_split(0, "better", -3.1, 0.01),
        _make_split(1, "worse", 2.8, 0.02),
    ]

    rendered = html_module.unescape(ValidationAuditRenderer().render(run, splits))

    assert "2. Methodology" in rendered
    for fact in METHODOLOGY_FACTS:
        assert fact in rendered


def test_methodology_section_sits_before_leakage_params_and_reproducibility_and_results_table():
    """Design acceptance criterion: "2. Methodology" sits before "2.1 This
    run's leakage-protocol parameter values", which sits before
    "Reproducibility statement", which sits before "3. Results table (per
    split)" -- proves the new section sits where Design says it must, not
    merely that it's present somewhere."""
    run = _make_run(status="completed")
    splits = [_make_split(0, "better", -3.1, 0.01)]

    html = ValidationAuditRenderer().render(run, splits)

    assert (
        html.index("2. Methodology")
        < html.index("leakage-protocol parameter values")
        < html.index("Reproducibility statement")
        < html.index("3. Results table (per split)")
    )


def test_methodology_facts_comes_from_the_shared_library():
    """`METHODOLOGY_FACTS` is re-exported from `libs/common`, not re-authored
    here -- the canonical wording and its exact-text assertion live in that
    package's own suite, so the two rendering services cannot drift apart.
    This test guards the import itself: a local re-definition would break the
    identity check even if the text happened to match."""
    assert METHODOLOGY_FACTS is shared_methodology_facts


def test_methodology_section_has_no_banned_positioning_words():
    """CLAUDE.md positioning scan, scoped to the new "2. Methodology" block
    only (the template's pre-existing disclaimer text legitimately uses
    "forecast"/"recommendations" elsewhere, so a whole-template scan would
    false-positive) -- mirrors dashboard-web's
    `test_help_concepts_page_has_no_banned_positioning_words` pattern."""
    run = _make_run(status="running")

    html = ValidationAuditRenderer().render(run, [])

    start = html.index("2. Methodology")
    end = html.index("Status", start)
    block = html[start:end].lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in block, f"banned positioning word {banned!r} found in Methodology block"
