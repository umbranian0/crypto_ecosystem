**Superseded**: this draft was produced by an earlier orchestration pass that stalled before Tech Lead
pickup (see the orchestrating-PM feedback note on background-agent stalling). The same scope was
re-sequenced and actually executed as `docs/sprints/sprint-35.md` (tickets VS-029/DASH-124/125/126/127/
GW-029, all done, QA-signed-off, live-verified). Kept here only as a historical record of the first
planning pass — do not pick up work from this file.

# Sprint 34 — dashboard-web disclosure/accessibility fixes + gateway-api OpenAPI correctness

Sprint goal: A reader of any run-detail page (sighted or screen-reader) can no longer mistake the
placeholder "Model" column or a hidden raw-levels-vs-returns tooltip for real model evidence, and an
external integrator following `gateway-api`'s published `openapi.json` gets the correct auth scheme for
`/runs` on the first call.

Backlog source: `docs/product/backlog-uat-findings.md` (approved, 10-persona UAT review, 14 stories,
Product Owner-groomed; no prior sprint has drawn from it).

## Stories in scope (execution order)

1. **UAT-001** — Label the placeholder "Model" column honestly [Must, dashboard-web + validation-service].
   Goes first: it's the only story in this sprint adding a new response field (`has_client_model` or
   equivalent) and editing `run_detail.html`'s "Model" column header. Nothing else in this sprint depends
   on it, but it touches `run_detail.html` before UAT-002/UAT-011 do, so it lands and is verified first to
   avoid three stories converging on the same file's diff at once.
2. **UAT-002** — Surface the raw-levels-vs-returns warning on every submission path [Must, dashboard-web].
   Second: edits `run_new.html` (adds a static always-visible notice) and `run_detail.html`'s disclaimer
   block (same file UAT-001 just touched — sequenced after UAT-001's edit is merged, not concurrent).
   No dependency on UAT-001's content, only a file-overlap ordering choice.
3. **UAT-011** — Make `data-tooltip` help text accessible via aria-label/aria-describedby [Must,
   dashboard-web]. Third, deliberately last of the three dashboard-web stories: it sweeps *every*
   remaining `data-tooltip` element across templates, including the ones UAT-002 just added visible text
   near (`run_new.html`, `run_detail.html`) and any others (e.g. horizon-unit hints). Running it after
   UAT-002 means it accessibility-annotates the final template state rather than markup UAT-002 is about
   to change underneath it. The Product Owner's own backlog note flags this bundling as natural (same
   template files, same disclosure-integrity concern as Epic 1); sequenced, not parallelized, to avoid a
   same-file clobber on `run_new.html`/`run_detail.html`.
4. **UAT-005** — Fix `openapi.json`'s incorrect `X-Operator-Token` scheme on `/runs` [Must, gateway-api].
   Independent module, zero file overlap with the dashboard-web chain above — can run in parallel with
   items 1–3 at the Tech Lead's discretion, or interleaved; no ordering constraint either way.
5. **Monitoring login-state-conflation bug** (`services/dashboard-web/src/app/templates/monitoring.html`
   line 106 / `operator.py`'s `_fetch_crawl_statuses`) — flagged by the Product Owner in the backlog file's
   "Confirmed small bug" section for direct Tech Lead pickup, not backlog grooming. Included in this
   sprint as a same-sprint small fix, tracked the way this repo already tracks "found live, fixed same
   sprint" items outside normal story numbering (see `docs/tickets/README.md`'s INF-019 and NFE-019
   precedents: a short dedicated subsection under the relevant module, not a formal ticket ID pulled from
   a backlog). Touches `monitoring.html`/`operator.py`, disjoint from `run_new.html`/`run_detail.html`, so
   it can run in parallel with items 1–3 and item 4 with no file-overlap risk.

## Stories explicitly deferred (from the same backlog, not in this sprint's scope)

- UAT-003, UAT-004 (Should, Epic 2) — deferred; UAT-003 also formally depends on UAT-001 landing first,
  which this sprint provides, but neither was requested in scope for this sprint.
- UAT-006, UAT-007 (Should, Epic 3) — deferred, gateway-api/validation-service error-path and schema
  polish, not requested in scope.
- UAT-008, UAT-009, UAT-010 (Should, Epic 4) — deferred, power-user run-management features, not
  requested in scope.
- UAT-012, UAT-013, UAT-014 (Could, Epics 5/6) — deferred, lower-severity accessibility/onboarding items,
  not requested in scope.

None of the deferred items block any story in this sprint's scope.

## Definition of done for this sprint

- All acceptance criteria checked for UAT-001, UAT-002, UAT-011, UAT-005, and the monitoring bug fix, as
  written in `docs/product/backlog-uat-findings.md` and (for the monitoring bug) as described in that
  file's "Confirmed small bug" section.
- Each dashboard-web story's own unit test (placeholder-label rendering, unconditional-warning-text scan,
  aria-label/aria-describedby coverage scan) passes; `gateway-api`'s `openapi.json` security-scheme test
  passes.
- Full `services/dashboard-web` and `services/gateway-api` suites re-run clean by the Tech Lead against
  the real diff (not a dev-agent self-report), zero regressions.
- `services/dashboard-web/README.md` and `services/gateway-api/README.md` status/contract sections updated
  to reflect the new `has_client_model` field, the always-visible warning, the aria-label coverage, the
  corrected OpenAPI security scheme, and the monitoring fix.
- `docs/tickets/README.md` gains a Sprint 34 entry for UAT-001/002/011/005 under
  `services/dashboard-web`/`services/gateway-api`, plus a short dedicated subsection for the monitoring
  bug fix mirroring the INF-019/NFE-019 "outside sprint numbering" precedent.
- QA gate (`qa` agent / `/qa-validation`) raised by the Tech Lead after all five items are done, before
  any production sign-off, per this session's standing process.
</content>
