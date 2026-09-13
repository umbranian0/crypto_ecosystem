# DASH-126 — UAT-002: raw-levels-vs-returns warning on every submission/viewing path

**Status: Done.** `run_new.html` gained a static, always-visible notice; `run_detail.html`'s existing
disclaimer paragraph was extended with the same sentence (byte-identical to the pre-existing
`dataset_reference_field` tooltip text, which is unchanged). 287 unit tests passing (up from 285
baseline), plus the same 7 e2e (not re-run by this ticket). See
`services/dashboard-web/README.md`'s "Raw-levels-vs-returns warning: always-visible notice (DASH-126)"
section for the full note.

**Module**: `services/dashboard-web` only.
**Depends on**: `DASH-125` for file-ordering only (both touch `run_detail.html`'s disclaimer block) — no
data/logic dependency. Must run after `DASH-125` lands, before `DASH-127`.

## Analysis

Covers `docs/product/backlog-uat-findings.md` UAT-002. The raw-levels-vs-returns warning currently exists
only inside `run_new.html`'s `dataset_reference_field` tooltip (`data-tooltip="... Naive0 (predicts 0) is
nonsensically wrong by construction on raw price levels ..."`), invisible unless a sighted user hovers that
one specific field. It must become an always-visible static notice on `run_new.html`, and be folded into
`run_detail.html`'s existing disclaimer paragraph (the "Benchmark comparison... validation/audit metrics
only" text RAV-002/003 already share, immediately above the per-split table per that template's current
structure — see `run_detail.html` line ~28).

## Design

**Pattern**: none — presentation-only, no new computation/field (UAT-002 AC4).

**DRY check**: grepped `run_new.html`/`run_detail.html`. The exact warning sentence exists today only inside
`dataset_reference_field`'s `data-tooltip` attribute — no second copy anywhere. Reuse that sentence verbatim
(or lightly adapted per UAT-002 AC1's own allowance) as the single source text for both the new static notice
and `run_detail.html`'s disclaimer — do not write two different wordings for the same caveat.

**Files touched**:
- `services/dashboard-web/src/app/templates/run_new.html`: add a static, always-visible `<p>` notice above
  the form (near the top, alongside the existing intro paragraph, or immediately above the "Dataset
  reference" fieldset) carrying the raw-levels-vs-returns warning text verbatim/lightly-adapted from the
  `dataset_reference_field` tooltip. The tooltip itself stays as-is (DASH-127 will make it accessible, not
  remove it) — this is additive, not a replacement.
- `services/dashboard-web/src/app/templates/run_detail.html`: extend the existing disclaimer paragraph
  (line ~28, `<p>Benchmark comparison of the model against the Naive0 baseline...</p>`) to also include the
  raw-levels-vs-returns warning sentence — either appended to that same `<p>` or as an adjacent `<p>`
  immediately after it, inside the same `{% if splits %}` block DASH-125 established, so it's visible
  whenever per-split results are shown.

## Implementation acceptance criteria

- [x] AC1 (UAT-002 AC1): the warning text is a static, always-visible notice on `run_new.html`, not gated
  behind hover-only tooltip discovery on one field.
- [x] AC2 (UAT-002 AC2): the same warning text appears in `run_detail.html`'s existing per-run disclaimer
  block.
- [x] AC3 (UAT-002 AC4): no new computation, no new field — presentation only; no Python handler logic
  changed (only the two Jinja templates).
- [x] AC4: does not remove or alter the existing `dataset_reference_field` tooltip's own warning text — DASH-127
  needs that tooltip's text intact to add accessible markup to.

## Test acceptance criteria

- [x] Unit test scanning rendered `run_new.html`/`run_detail.html` output and asserting the raw-levels warning
  text is present unconditionally in the rendered HTML body (not only inside a `data-tooltip` attribute
  value) — matching UAT-002's own AC3 wording exactly.
- [x] Full `services/dashboard-web` suite re-run, zero regressions (287 passed, 7 deselected -- baseline
  was 285 passed, 7 deselected).

## Review acceptance criteria (Tech Lead verifies personally)

- Confirm the warning text used in both new locations is the same sentence (or a disclosed, lightly-adapted
  variant), not two independently-worded caveats.
- Confirm no CLAUDE.md positioning-rule violation in the new copy (still describes Naive0's behavior on raw
  levels, not a prediction/signal claim).
- Confirm this lands cleanly on top of `DASH-125`'s already-merged disclaimer-block layout, not fighting it
  (read both diffs together before marking done).

## Documentation acceptance criteria

- `services/dashboard-web/README.md`: note that the raw-levels-vs-returns warning is now always-visible on
  both the submission and viewing paths (previously tooltip-only).
- `docs/product/backlog-uat-findings.md`: UAT-002's acceptance-criteria boxes checked, pointing at this
  ticket.
