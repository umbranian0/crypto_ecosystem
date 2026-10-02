# CHORE-66-03 -- reporting-service PDF: no table row split across pages

**Status: done.** Sprint 66 item 3. Module: services/reporting-service.

## Analysis
Sprint 63 QA follow-up: a table row may break across a page. `src/app/renderers/pdf.py` `_PDF_CSS` has no row-break rule.

## Design
Add `tr { page-break-inside: avoid; break-inside: avoid; }` to `_PDF_CSS`. No layout redesign, no new abstraction.

## Implementation AC
Rule present in the stylesheet applied to the PDF.

## Test AC
One test asserting the rule is in the stylesheet (WeasyPrint native libs are unavailable on host, so render tests skip; the assertion must not need them). Full reporting suite green.

## Review AC (TL)
Read diff; rerun suite. Visual verification is QA's job on the rebuilt container.

## Documentation AC
reporting-service README PDF section: one line on row-break avoidance.

## Rules
Never run tests, alembic or SQL against the live database `naive_first`; Postgres-backed tests target `naive_first_test`. Do not git commit. Stay in the module.
