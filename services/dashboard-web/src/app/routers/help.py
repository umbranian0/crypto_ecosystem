"""UAT-014: `GET /help/concepts` -- a plain-language explainer page for
purge gap / walk-forward windows.

Single responsibility: pure static render, no downstream call, no session
requirement (matches `run_new_form`'s style of static-page render, minus the
dataset fetch that page needs and this one doesn't). Distinct concern from
`app.routers.runs` (which owns `/runs/*` and `/datasets`) -- this repo's
router-per-concern convention (`auth.py`, `settings.py`, `setup.py`,
`operator.py` each own their own concern) is followed here rather than
appending a fifth unrelated route to `runs.py`, since this page has no
relationship to a run/dataset request/response cycle at all.

Positioning: this page's own copy must never use "prediction"/"signal"/
forecast-of-future-price language (CLAUDE.md) -- it explains the validation
protocol's own mechanics (purge gap, walk-forward windows), not what any
model's output means.

TRUST-002: `GET /help/leakage-demo` -- a second static route on this same
router (same "help/explainer pages" concern this file's own docstring already
claims, not a new sibling file). Same pure-render, no-downstream-call,
no-session pattern as `/help/concepts` above. Displays the thesis's own real
1h/6h/24h numbers from `docs/da-tese-ao-produto.md` section 1.3 verbatim (no
fabricated or illustrative-only figures) side by side with a descriptive,
didactic account of what the purge-gap/train-only-fit protocol protects
against -- never a fabricated leaky re-run of the thesis, which does not
exist. Linked from `_methodology_panel.html` (TRUST-001-01, already in place)
and from `help_concepts.html` (this ticket).
"""

from __future__ import annotations

from fastapi import APIRouter, Request

from app.main import templates

router = APIRouter()


@router.get("/help/concepts")
def help_concepts(request: Request):
    """Pure static render -- no downstream call, no session dependency (this
    page explains platform mechanics, not tenant-specific data, so there is
    nothing here that needs to be gated behind login)."""
    return templates.TemplateResponse(request, "help_concepts.html", {})


@router.get("/help/leakage-demo")
def help_leakage_demo(request: Request):
    """TRUST-002: static, no downstream call, no session dependency -- same
    pattern as `help_concepts` above."""
    return templates.TemplateResponse(request, "help_leakage_demo.html", {})
