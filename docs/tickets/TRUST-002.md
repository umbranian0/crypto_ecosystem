# TRUST-002 — Static "leaky vs. purged walk-forward" demo using the thesis's own numbers

**Module**: `services/dashboard-web` only.
**Depends on**: `TRUST-001-01` and `TRUST-005-01` must both be `done` (Tech-Lead-verified) before
this starts — sequenced last per the sprint plan (its one real precondition is a rendered
`TRUST-001` panel to link *from*; also avoids concurrent edits to `run_detail.html`/`runs.py` while
those two are still in flight in the same service).
**Story**: `docs/product/backlog-trust-and-admin-ops.md` TRUST-002 (Should).
**Status: done.** Implemented, tested (5 new tests: `test_help_leakage_demo_returns_200_and_expected_numbers`,
`test_help_concepts_links_to_leakage_demo`, `test_help_leakage_demo_page_has_no_banned_positioning_words`,
`test_help_leakage_demo_restates_core_finding` in `tests/test_help_concepts.py`, plus
`test_run_detail_links_to_leakage_demo` in `tests/test_runs_detail.py`), full `services/dashboard-web`
suite personally re-run by the Tech Lead (402 passed, 0 failed, 8 deselected, `-m "not e2e"`, up from
394 pre-sprint), Tech-Lead-reviewed (diff read personally, numbers re-verified directly against
`docs/da-tese-ao-produto.md` section 1.3 a second time at Review, both inbound links confirmed to
resolve to `200` via `client.get`, positioning copy read in full).

**Outcome**: this was the sprint's highest-priority item -- the `<a href="/help/leakage-demo">` link
`TRUST-001-01` shipped on every run-detail page 404'd because this route did not exist. `GET
/help/leakage-demo` (`services/dashboard-web/src/app/routers/help.py`) and its template
(`services/dashboard-web/src/app/templates/help_leakage_demo.html`) now exist exactly as designed
below: pure static render, no session/downstream dependency, the real 1h/6h/24h Naive0/OLS MAE, OLS DA,
and DM better/worse figures from section 1.3 (verified verbatim a second time at Review), a
descriptive/didactic "what a leaky evaluation would have reported" paragraph explicitly stating no
fabricated leaky re-run exists or is computed, and a closing paragraph restating the core finding
("no model beat Naive0" plus the 52.51% DA figure). `help_concepts.html` gained one new closing
paragraph linking to it. The Analysis section's positioning note required one correction during
implementation: the first draft's "Bitcoin return-prediction case study" phrase tripped the banned-word
scan (the word "prediction" in isolation, not describing the platform's own function) and was reworded
to "return-modeling case study" -- a wording fix, not a scope change.

## Analysis

Covers TRUST-002's full AC. Verified directly against `services/dashboard-web/src/app/routers/
help.py` (read in full): `GET /help/concepts` is a standalone `APIRouter()` in this file, a pure
`templates.TemplateResponse(request, "help_concepts.html", {})` call — no session/auth dependency,
no downstream service call. This ticket's `/help/leakage-demo` is a second route on this same
router file (same "help/explainer pages" concern `help.py`'s own docstring already claims — not a
new concern requiring a sibling file).

**Numbers verified directly against `docs/da-tese-ao-produto.md` section 1.3** (read in full — do
not re-derive from memory, use these exact figures, all already published in that file):

| Horizon | Naive0 MAE | OLS MAE (vs. Naive0) | OLS DA | DM (better/worse vs. Naive0) |
|---|---|---|---|---|
| 1h | 0.003627 | 0.003683 (+1.55%) | 51.33% | 0/4 |
| 6h | 0.009110 | 0.009533 (+4.64%) | 52.51% | 4/18 |
| 24h | 0.019720 | 0.020895 (+5.96%) | 50.80% | 14/22 |

(Section 1.4's own stated conclusions, also citable verbatim: "Naive0 venceu em MAE/RMSE médios nos
três horizontes. Nenhum modelo não-naive foi consistentemente melhor." / OLS was the best
non-naive challenger but stayed above Naive0 at every horizon / best DA observed = 52.51% (OLS,
6h), marginal above chance (50%) / DM evidence "mixed and limited" — OLS had more "worse" than
"better" splits against Naive0 at nearly every horizon. English paraphrase is fine for the page's
copy; the *numbers* must match verbatim.)

Section 1.2's experimental-design table is the source for the "what the purge-gap/train-only-fit
protocol protects against" side: purge gap 24h, rolling-origin walk-forward, preprocessing
restricted to the training fold per split.

## Design

**Pattern**: none of Strategy/Repository/Adapter/Factory/Observer applies — pure static render,
same pattern `/help/concepts` already established.

**Files touched** (scoped to `services/dashboard-web` only):
- `services/dashboard-web/src/app/routers/help.py` — add a second route:

  ```python
  @router.get("/help/leakage-demo")
  def help_leakage_demo(request: Request):
      """TRUST-002: static, no downstream call, no session dependency -- same
      pattern as help_concepts above."""
      return templates.TemplateResponse(request, "help_leakage_demo.html", {})
  ```
- `services/dashboard-web/src/app/templates/help_leakage_demo.html` (new, `{% extends "base.html"
  %}`, same structure as `help_concepts.html`): a side-by-side comparison using the table above
  (real numbers, verbatim), plus:
  - A "what a leaky evaluation would have reported" paragraph, explicitly labeled
    descriptive/didactic (e.g. "a naive random-split or globally-fit-preprocessing evaluation would
    not purge the boundary between train and test data the way this platform's protocol does — the
    numbers in the 'purged' column above are what this platform's own leakage-aware protocol
    actually reported for the same models; no leaky re-run of the thesis exists or is computed by
    this platform, so there is no second, independently-computed 'leaky' number to show — this
    section describes the mechanism the purge gap protects against, using the published research's
    own account of it (section 1.2/1.5), not a fabricated comparison figure").
  - A closing paragraph restating the core finding plainly: no model beat Naive0 in a stable,
    significant way at any tested horizon; best directional accuracy observed was 52.51% (OLS, 6h),
    barely above chance.
  - A link back to `/help/concepts`.
- `services/dashboard-web/src/app/templates/help_concepts.html` — add one link to
  `/help/leakage-demo` (e.g. a new closing paragraph or list item under "Why this matters").
- `services/dashboard-web/src/app/templates/_methodology_panel.html` (from `TRUST-001-01`) — the
  link to `/help/leakage-demo` this ticket's own route now makes resolvable was already added by
  `TRUST-001-01`; this ticket does not need to touch that file again unless `TRUST-001-01`'s Review
  found the link text needs adjustment (check before editing — avoid an unnecessary diff).

**DRY check** (performed before writing this ticket): grepped `services/dashboard-web/src/app/
routers` for a second `APIRouter()` pattern matching `help.py`'s static-render style — none beyond
`help.py` itself; no existing "side-by-side comparison table" template to reuse (this is the first
one), so a new template is justified, not a duplicate of an existing mechanism.

## Implementation acceptance criteria

- `GET /help/leakage-demo` returns `200` with no session/auth requirement and no downstream service
  call (mirrors `/help/concepts` exactly).
- The page displays the real 1h/6h/24h numbers from the table above, verbatim (not rounded/altered
  beyond what section 1.3 itself already shows).
- The "leaky" side is described as descriptive/didactic (what the purge-gap/train-only-fit protocol
  protects against), explicitly stating no fabricated leaky re-run exists or is computed by this
  platform — never presented as a second, independently-measured number.
- The page explicitly reinforces the core finding (no model beat naive stably) — closing paragraph
  states this plainly, matching CLAUDE.md's "Core finding" section wording in spirit.
- Positioning check: no "prediction"/"forecast"/"signal"/"recommendation" anywhere on the page
  (reuse the banned-word-scan convention); the page never reads as "buy this model" (read the
  actual copy, not just the word scan — the page's framing must sell validation discipline, not any
  model's output).
- `/help/leakage-demo` is linked from `_methodology_panel.html` (already added in `TRUST-001-01`;
  verify it resolves now that this route exists) and from `/help/concepts` (added by this ticket).

## Test acceptance criteria

- `test_help_leakage_demo_returns_200_and_expected_numbers`: asserts `200` and that the response
  text contains the real MAE/DA/DM figures for all three horizons (e.g. `"0.003683"`, `"51.33"`,
  `"0/4"`, `"0.009533"`, `"52.51"`, `"4/18"`, `"0.020895"`, `"50.80"`, `"14/22"` — exact strings
  from section 1.3, not paraphrased).
- `test_help_concepts_links_to_leakage_demo`: `GET /help/concepts` response contains
  `href="/help/leakage-demo"`.
- `test_run_detail_links_to_leakage_demo` (or extend an existing methodology-panel test from
  `TRUST-001-01`): `GET /runs/{run_id}` response contains `href="/help/leakage-demo"`, and a
  follow-up `client.get` to that href returns `200` (proves the link actually resolves, not just
  that the `<a>` tag exists).
- `test_help_leakage_demo_page_has_no_banned_positioning_words`: scans
  `help_leakage_demo.html` for `("prediction", "forecast", "signal", "recommendation")`, mirroring
  `test_help_concepts_page_has_no_banned_positioning_words`.
- `test_help_leakage_demo_restates_core_finding`: asserts the rendered page contains language
  matching the core finding (e.g. asserts presence of "did not beat" or "no model beat" plus
  "Naive0" and the "52.51" DA figure) — a simple content-presence check, not a full-text match.
- Full existing `services/dashboard-web` suite still passes.

## Review acceptance criteria (Tech Lead verifies personally)

- Read the actual diff of `help.py`, `help_leakage_demo.html`, `help_concepts.html`, and the test
  file(s).
- **Personally re-verify every number cited on the page against `docs/da-tese-ao-produto.md`
  section 1.3**, reading that section directly again at Review time (not trusting the dev agent's
  transcription) — this is the ticket's single highest-scrutiny item per the sprint's Definition of
  Done.
- Confirm the "leaky" side's copy reads as descriptive/didactic, not as a fabricated re-run — read
  the actual sentence, not just check for a disclaimer's presence.
- Confirm the page's overall framing reinforces, never contradicts, the core finding — read the
  full rendered copy, not just the closing paragraph.
- Confirm both inbound links (`/help/concepts` → this page, `_methodology_panel.html` → this page)
  actually resolve to `200`, not just that the `href` string is present.
- Run `uv run pytest -m "not e2e" -q` in `services/dashboard-web` personally and confirm zero
  regressions plus new tests passing.

## Documentation acceptance criteria

- `services/dashboard-web/README.md` gains a new subsection ("Leakage demo page (TRUST-002)") near
  the existing "`/help/concepts`" documentation: route, no-backend-call/no-session pattern, the
  real numbers sourced from `docs/da-tese-ao-produto.md` section 1.3, and both inbound links.
- `docs/tickets/README.md` gains a TRUST-002 row once Review passes.
