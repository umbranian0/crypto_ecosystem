"""ECON-006: pytest entry point for `scripts/check_profitability_language.py`.

Mirrors NFE-018/LC-005/VS-016's own `tests/test_doc_sync.py` precedent (a
thin pytest wrapper around the standalone script's `check()` function, so
both `python scripts/check_profitability_language.py` and `pytest` catch the
same drift).
"""

from __future__ import annotations

import sys
from pathlib import Path

SCRIPTS_DIR = Path(__file__).resolve().parent.parent / "scripts"
if str(SCRIPTS_DIR) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_DIR))

from check_profitability_language import (  # noqa: E402
    _EXEMPT_MODULE,
    _scan_text,
    check,
    collect_scan_targets,
)


def test_no_profitability_claim_language_outside_eligibility_module():
    messages = check()
    assert messages == [], (
        "Forbidden profitability-claim language found outside "
        "src/app/eligibility.py:\n" + "\n".join(messages)
    )


def test_eligibility_module_is_excluded_from_the_scan():
    assert _EXEMPT_MODULE not in collect_scan_targets()


def test_scan_flags_an_unhedged_profitability_claim():
    hits = _scan_text("fake_module.py", 'This model is profitable and beats the market.')

    assert len(hits) == 2
    assert any("profitable" in hit for hit in hits)
    assert any("beats the market" in hit for hit in hits)


def test_scan_allows_the_curated_negated_exceptions():
    hits = _scan_text(
        "README.md",
        "must never be read as evidence the platform currently has a "
        "profitable model",
    )

    assert hits == []


def test_scan_does_not_flag_the_word_profitability_itself():
    hits = _scan_text("fake_module.py", "a profitability figure is never stored here")

    assert hits == []


def test_scan_does_not_flag_bare_return_vocabulary():
    hits = _scan_text(
        "fake_module.py",
        "cost_adjusted_return and slippage_adjusted_return are numeric fields",
    )

    assert hits == []


def test_backtests_router_is_covered_by_the_existing_glob_with_no_code_change():
    """ECON-014: `routers/backtests.py` (ECON-012) and any file ECON-013 adds
    under `repositories/`/`models.py` are already covered by
    `collect_scan_targets()`'s existing, unconditional, recursive
    `SRC_APP_DIR.rglob("*.py")` glob -- confirmed directly here rather than
    trusted from the ticket's own DRY-check note. No second, parallel
    file-list mechanism is added; this test only proves the existing one
    already reaches the new file."""
    backtests_router = SCRIPTS_DIR.parent / "src" / "app" / "routers" / "backtests.py"

    assert backtests_router.exists()
    assert backtests_router in collect_scan_targets()


def test_drift_detection_catches_and_recovers_from_an_injected_forbidden_word():
    """ECON-014's required real, performed-live demonstration (mirrors
    ECON-006's own precedent exactly): inject a forbidden word into
    `routers/backtests.py` (an ECON-012 file, in scope for this ticket),
    confirm the check fails and reports the exact hit, revert the file, and
    confirm the check passes again.

    `routers/backtests.py` is untracked in this repo's current git state (it
    is ECON-012's own not-yet-committed new file), so `git diff` against it
    is not a meaningful "zero residual change" check here -- an untracked
    file never shows in `git diff`'s tracked-file comparison regardless of
    its contents. The authoritative revert-confirmation this test performs
    instead is a direct byte-for-byte comparison of the file's contents
    against the value captured before injection.
    """
    backtests_router = SCRIPTS_DIR.parent / "src" / "app" / "routers" / "backtests.py"
    original_text = backtests_router.read_text(encoding="utf-8")
    injected_word = "profit"
    injected_line = "# ECON-014 drift-detection demonstration: this model is profit.\n"

    try:
        backtests_router.write_text(original_text + injected_line, encoding="utf-8")

        hits = check()
        assert any(
            "backtests.py" in hit and injected_word in hit for hit in hits
        ), f"expected an injected-word hit against backtests.py, got: {hits}"
    finally:
        backtests_router.write_text(original_text, encoding="utf-8")

    reverted_text = backtests_router.read_text(encoding="utf-8")
    assert reverted_text == original_text, "revert left residual change in backtests.py"

    assert check() == []
