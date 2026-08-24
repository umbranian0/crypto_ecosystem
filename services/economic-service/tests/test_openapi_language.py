"""ECON-014: verifies the *actual generated* OpenAPI schema for
`POST /backtests` (ECON-012), not just the router's docstring source.

`ECON-006` mechanically scanned prose in `README.md` and every `.py` file
under `src/app` (except `eligibility.py`) for forbidden profitability-claim
language, but never separately re-verified FastAPI's own generated
`/openapi.json` output -- summary/description strings are hand-authored in
the router's `@router.post(...)` call, and nothing structurally guarantees
what's on disk survives unmodified into the schema FastAPI actually serves
at `/docs`/`/openapi.json` (a future refactor could, for instance, override
`summary`/`description` via `openapi_extra` or a custom `generate_unique_id`
without ECON-006's own scan ever seeing the new value, since that scan reads
source files, not the generated schema). This module closes that gap: it
boots the real `app`, calls `app.openapi()` for real, and asserts the
generated `summary`/`description` fields for `POST /backtests` contain the
required retrospective/hypothetical framing and none of the forbidden
forward-looking terms.

No OpenAPI-scanning test already existed anywhere in `tests/` for
`POST /simulations` either (confirmed by grepping for `openapi()` and
`/openapi.json` in this directory before writing this file) -- so this is a
new file, not an extension of an existing one, per the ticket's own
"check first" instruction.
"""

from __future__ import annotations

import re

from fastapi.testclient import TestClient

from app.main import app

_REQUIRED_FRAMING_PATTERNS = [
    re.compile(r"\bhypothetical\b", re.IGNORECASE),
    re.compile(r"\bretrospective\b", re.IGNORECASE),
    re.compile(r"\bresearch purposes\b", re.IGNORECASE),
]

# Word-boundaried, mirroring check_profitability_language.py's own
# `_FORBIDDEN_PATTERNS` shape -- forward-looking/promotional senses only.
# Bare "returns" is deliberately excluded: it is this codebase's normal,
# legitimate domain vocabulary (`cost_adjusted_return`, "cost/slippage-
# adjusted returns") and appears correctly in this endpoint's own
# description; only the promotional/forward-looking terms below are
# actually forbidden here, matching the ticket's own listed set
# ("returns"/"profit"/"win" in a *promotional or forward-looking* sense --
# operationalized here as the bare adjective/verb forms that assert a
# current or future gain, not the neutral noun already in legitimate use).
_FORBIDDEN_FORWARD_LOOKING_PATTERNS = {
    "profit": re.compile(r"\bprofit(?:able)?\b", re.IGNORECASE),
    "win": re.compile(r"\bwin(?:s|ning)?\b", re.IGNORECASE),
}


def _get_backtests_operation() -> dict:
    client = TestClient(app)
    response = client.get("/openapi.json")
    assert response.status_code == 200

    schema = response.json()
    assert "/backtests" in schema["paths"], schema["paths"].keys()

    operation = schema["paths"]["/backtests"]["post"]
    return operation


def test_openapi_schema_is_reachable_via_app_openapi_and_via_the_real_endpoint():
    generated = app.openapi()
    assert "/backtests" in generated["paths"]

    served = _get_backtests_operation()
    assert served == generated["paths"]["/backtests"]["post"]


def test_backtests_openapi_summary_and_description_use_required_framing():
    operation = _get_backtests_operation()
    summary = operation.get("summary", "")
    description = operation.get("description", "")
    combined = f"{summary}\n{description}"

    matched = [p for p in _REQUIRED_FRAMING_PATTERNS if p.search(combined)]
    assert matched, (
        "POST /backtests's generated summary/description must contain at "
        "least one of hypothetical/retrospective/'research purposes':\n"
        f"{combined!r}"
    )


def test_backtests_openapi_summary_and_description_have_no_forbidden_forward_looking_terms():
    operation = _get_backtests_operation()
    summary = operation.get("summary", "")
    description = operation.get("description", "")
    combined = f"{summary}\n{description}"

    hits = {
        term: pattern.findall(combined)
        for term, pattern in _FORBIDDEN_FORWARD_LOOKING_PATTERNS.items()
        if pattern.search(combined)
    }
    assert hits == {}, (
        "POST /backtests's generated summary/description must never use "
        f"promotional/forward-looking terms, found: {hits} in {combined!r}"
    )
