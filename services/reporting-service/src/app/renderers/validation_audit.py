"""RS-003: `ValidationAuditRenderer` -- the one real report kind this
backlog ships (`"validation_audit"`, RS-105/certification-seal is a
documented Won't per `docs/product/backlog-reporting-service.md` decision 7).

Renders the `naive-first-audit` skill's report structure (Scope /
leakage-protocol-parameters / Results table / Verdict / mandatory
statistical-accuracy-vs-economic-value disclaimer / Recommendations)
programmatically from a `RunDetailResponse` + its `SplitResultResponse`
list, via Jinja2 (`templates/validation_audit.html.jinja`).

This renderer does not itself re-derive a leakage pass/fail checklist --
computing/checking leakage is validation-service's/naive_first_engine's
bounded context, not this service's ("Does not own", README). It states
what protocol parameters the run actually used (`purge_gap_hours`, `horizon`)
verbatim, which is the "Leakage check" section's factual basis without this
service independently re-judging pass/fail.

No metric or DM-verdict field is recomputed, re-thresholded, or
re-interpreted anywhere in this module or the template it renders -- every
`model_*`/`naive0_*`/`dm_*` value from `SplitResultResponse` is passed to the
template unchanged (ticket RS-003 Design section, extra-scrutiny flag).
"""

from __future__ import annotations

from pathlib import Path

from jinja2 import Environment, FileSystemLoader, select_autoescape
from naive_first_common.contracts import RunDetailResponse, SplitResultResponse

from app.renderers.base import ReportRenderer

# TRUST-001-02: byte-identical to dashboard-web's TRUST-001-01 `METHODOLOGY_FACTS`
# (copied verbatim, not imported -- no cross-service import, implementation-plan.md
# section 2). A same-text test in this service's suite guards drift.
METHODOLOGY_FACTS: tuple[str, str, str, str] = (
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

_TEMPLATES_DIR = Path(__file__).resolve().parent.parent / "templates"

_env = Environment(
    loader=FileSystemLoader(str(_TEMPLATES_DIR)),
    autoescape=select_autoescape(["html", "jinja"]),
)


class ValidationAuditRenderer(ReportRenderer):
    def render(
        self,
        run: RunDetailResponse,
        splits: list[SplitResultResponse],
        *,
        narrative_html: str | None = None,
    ) -> str:
        template = _env.get_template("validation_audit.html.jinja")
        return template.render(
            run=run,
            splits=splits,
            narrative_html=narrative_html,
            methodology_facts=METHODOLOGY_FACTS,
        )
