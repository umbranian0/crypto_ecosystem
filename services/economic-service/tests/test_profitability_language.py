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
