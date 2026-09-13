# DASH-127 — UAT-011: accessible markup for every `data-tooltip` element

**Module**: `services/dashboard-web` only.
**Depends on**: `DASH-126` (must run after it, so accessible markup is added to the final tooltip text, not
text that gets edited out from under it). Last of the three Track A tickets.

## Analysis

Covers `docs/product/backlog-uat-findings.md` UAT-011. Every existing `data-tooltip` element (in `run_new.html`
and any other template using this pattern — grep to confirm full list, don't assume `run_new.html` is the
only file) needs an `aria-label` (or `aria-describedby` pointing at a visually-hidden element with the same
text) carrying the same tooltip text, so a screen reader announces it without requiring a mouse hover. No
visual change for sighted users.

## Design

**Pattern**: none — additive ARIA markup only.

**DRY check**: grep `data-tooltip=` across `services/dashboard-web/src/app/templates/`. Confirm the full set
of elements first (this ticket's Design assumption is `run_new.html`'s `<span class="field-tooltip"
tabindex="0" data-tooltip="...">?</span>` pattern, one per labeled field — do not touch elements this grep
doesn't find). Use `aria-label="{{ same text as data-tooltip }}"` on the same `<span>` element (simplest
option, avoids introducing a second visually-hidden DOM node per tooltip) unless a tooltip's text is long
enough that `aria-label` best-practice recommends `aria-describedby` + a visually-hidden sibling element
instead (Tech Lead's call per element, document the choice).

**Files touched**: every template found by the grep above — expected to be `run_new.html` (multiple
`field-tooltip` spans) at minimum, plus whatever `DASH-126` added in `run_new.html`/`run_detail.html` if
those additions used the same `data-tooltip` pattern (confirm; if `DASH-126`'s new notices are plain static
`<p>` text, not `data-tooltip` elements, they need no ARIA markup — they're already always-visible/
announced, per DASH-126's own design, which is the whole point of that ticket).

## Implementation acceptance criteria

- AC1 (UAT-011 AC1): every existing `data-tooltip` element gains an `aria-label` (or `aria-describedby` +
  visually-hidden text) carrying the same tooltip text.
- AC2 (UAT-011 AC3): no visual change for sighted users — confirm no CSS changed, only HTML attributes added.
- AC3: covers the raw-levels-vs-returns tooltip (`dataset_reference_field`) specifically, since that's the
  one UAT-011's rationale calls out by name, plus every other `data-tooltip` element found by the grep — not
  a partial fix.

## Test acceptance criteria

- Unit test scanning rendered templates and asserting every element with a `data-tooltip` attribute has a
  corresponding `aria-label`/`aria-describedby` on the same element, with matching text content.
- Full `services/dashboard-web` suite re-run, zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Personally grep the final rendered templates for `data-tooltip` and confirm zero elements lack the
  matching ARIA attribute.
- Confirm no visual/CSS regression (diff review — no `style.css` change expected).
- Confirm this ran after `DASH-126`'s final tooltip text, not a stale pre-`DASH-126` version.

## Documentation acceptance criteria

- `services/dashboard-web/README.md`: note the accessibility convention (every `data-tooltip` element must
  carry a matching `aria-label`/`aria-describedby`) as a standing convention for any future tooltip added to
  this service — not just a one-time fix.
- `docs/product/backlog-uat-findings.md`: UAT-011's acceptance-criteria boxes checked, pointing at this
  ticket.
