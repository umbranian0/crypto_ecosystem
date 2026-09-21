"""The canonical exact-text assertion for shared disclosure copy.

This is the single place the methodology wording is pinned. `dashboard-web`
and `reporting-service` each assert only that they render *this* constant
(identity, not text), so editing a fact here is a deliberate one-line change
that fails this test until the expected text is updated with it -- rather than
two services quietly drifting apart on what they tell a tenant.
"""

from __future__ import annotations

from naive_first_common.disclosures import (
    METHODOLOGY_FACTS,
    NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE,
)


def test_methodology_facts_exact_wording():
    assert METHODOLOGY_FACTS == (
        "Rolling-origin walk-forward validation: each split trains on data up to a point in "
        "time and tests only on the period immediately after it -- never on rows the model "
        "could not yet have seen.",
        "A configurable purge gap separates every split's training window from its test "
        "window, closing the boundary-leakage channel a plain train/test split allows.",
        "Every run is benchmarked against the mandatory Naive0 and NaiveLast baselines -- a "
        "model's result is never reported in isolation.",
        "Model-vs-baseline comparisons use the Diebold-Mariano test with the Harvey et al. "
        "(1997) long-run variance correction for overlapping horizons, not a raw metric "
        "difference.",
    )


def test_methodology_facts_has_no_banned_positioning_words():
    """CLAUDE.md positioning constraint: this platform validates models, it
    does not predict prices. These four facts describe protocol mechanics only.
    """
    joined = " ".join(METHODOLOGY_FACTS).lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in joined, f"banned positioning word {banned!r} in METHODOLOGY_FACTS"


def test_not_beating_naive_sentence_exact_wording():
    """TRUST-005: the single place this shared sentence's exact text is
    pinned. `dashboard-web` and `reporting-service` each assert only identity
    with this constant (mirroring `test_methodology_facts_exact_wording`
    above) -- a local re-definition in either service fails even if its text
    happens to match.
    """
    assert NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE == (
        "Under rigorous, leakage-free validation, most models -- including sophisticated ones -- "
        "do not beat a strong naive baseline in a stable way; this platform's own published "
        "research found the same pattern, so this outcome is common and not evidence of a broken "
        "evaluation."
    )


def test_not_beating_naive_sentence_has_no_banned_positioning_words():
    """CLAUDE.md positioning constraint, same convention as
    `test_methodology_facts_has_no_banned_positioning_words`. This sentence
    must never imply a model *should* beat naive -- only that not beating it
    is expected and valid.
    """
    joined = NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE.lower()

    for banned in ("prediction", "forecast", "signal", "recommendation"):
        assert banned not in joined, (
            f"banned positioning word {banned!r} in NOT_BEATING_NAIVE_IS_EXPECTED_SENTENCE"
        )
