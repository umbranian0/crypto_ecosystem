"""AI-003: post-generation banned-term guard + pre-generation out-of-scope
refusal (ticket Design section).

`BANNED_TERMS` is deliberately module-local, an exact copy of AI-002's own
six-word list (`services/reporting-service/src/app/narrative/fact_check.py`)
rather than a cross-service import -- see AI-003-REFACTOR's Design section
for why only the hosted-API client (`libs/ai_assist`) was extracted into a
shared lib, not this guardrail: this list is small, service-owned copy, not a
shared contract, and each service is free to diverge (e.g. add a service-
specific term) without touching the other.

`is_out_of_scope` is a small, deterministic keyword heuristic (guardrail, not
full NLU, same precedent as AI-002's `fact_check.py` docstring) run *before*
any model call -- an out-of-scope question never reaches the hosted API.
"""

from __future__ import annotations

BANNED_TERMS = ("signal", "buy", "sell", "profit", "trade", "recommendation")

# Future-tense/speculative cues, combined with a price-direction cue, flag a
# question as asking this assistant to predict rather than explain past
# results (e.g. "will Bitcoin go up next week").
_FUTURE_CUES = ("will", "next week", "next month", "next year", "tomorrow", "future")
_PRICE_DIRECTION_CUES = (
    "go up",
    "go down",
    "price",
    "rise",
    "fall",
    "increase",
    "decrease",
)
_ALWAYS_OUT_OF_SCOPE_KEYWORDS = ("predict", "forecast")


def contains_banned_term(text: str) -> str | None:
    """Returns the first banned term found (case-insensitive substring
    match) in `text`, or `None` if none are present.
    """
    lowered = text.lower()
    for term in BANNED_TERMS:
        if term in lowered:
            return term
    return None


def is_out_of_scope(question: str) -> bool:
    """`True` for a question asking this assistant to predict/forecast
    prices/markets rather than explain the tenant's own stored validation
    history -- checked before any model call (ticket Design section).
    """
    lowered = question.lower()
    if any(keyword in lowered for keyword in _ALWAYS_OUT_OF_SCOPE_KEYWORDS):
        return True

    has_future_cue = any(cue in lowered for cue in _FUTURE_CUES)
    has_price_direction_cue = any(cue in lowered for cue in _PRICE_DIRECTION_CUES)
    return has_future_cue and has_price_direction_cue
