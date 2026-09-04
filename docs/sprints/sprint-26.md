# Sprint 26 — Run analysis visualization, Epic A (dashboard-web audit charts)

Sprint goal: a tenant viewing a completed run's detail page in `services/dashboard-web` can visually
see, without reading the raw per-split table, how the model's error compared to Naive0 and what the
Harvey-corrected DM test concluded for each split.

Backlog source: `docs/product/backlog-run-analysis-visualization.md` (RAV-001 through RAV-010).

## Stories in scope, in execution order

1. **RAV-001** — Decide dashboard-web's charting approach (client-side JS vs. server-rendered SVG)
   [Must]. Sequenced first because it is a hard blocking dependency, not a priority artifact: the
   backlog itself states RAV-002 through RAV-005 and RAV-009/RAV-010 "cannot be estimated" until this
   resolves. No prior sprint work depends on it; it has zero dependencies of its own. This is a
   decision deliverable (ADR or dated README section), not a shippable chart, but it gates every other
   story below and must close before implementation of any chart starts.
2. **RAV-002** — Model-vs-Naive0 error comparison chart across a run's splits [Must]. Depends on
   RAV-001's decision. Uses only data `run_detail.html` already fetches via the existing
   `GET /runs/{id}/splits` call (no backend/schema change) — the highest-value, lowest-cost story in
   the backlog, and the first half of the "audit a run visually" capability.
3. **RAV-003** — DM-test verdict visualization per split [Must]. Depends on RAV-001's decision (same
   blocking dependency as RAV-002; independent of RAV-002 itself — different chart, same fetched data,
   no shared new state). Completes the "audit a run visually" capability RAV-002 only half-covers
   (error magnitude without significance is incomplete, per the backlog's own rationale) and directly
   visualizes the platform's core differentiator (rigorous DM testing against Naive0).

Both RAV-002 and RAV-003 depend only on RAV-001, not on each other, so once RAV-001 closes they can be
sequenced in either order or run in parallel if the Tech Lead's file-collision review of
`run_detail.html`/`style.css` supports it — that call belongs to the Tech Lead's ticket breakdown, not
this plan.

## Stories explicitly deferred

- **RAV-004, RAV-005, RAV-009, RAV-010 (Should)** — deferred to a follow-up sprint (candidate:
  Sprint 27), not silently dropped. Reasoning: none of the three Must stories above needs any of these
  to ship a complete, coherent capability (a tenant can already audit a run's error and DM outcomes
  visually once RAV-001–003 land); RAV-004/005 are incremental extensions of RAV-002/003 (more metric
  pairs, an optional third series for client-supplied baselines) and RAV-009/010 open a second,
  separate page-level epic (cross-run trends) rather than deepening this one. No team size/velocity was
  given for this sprint, and this repo's own convention is not to guess a story-point capacity — rather
  than assume all four Should stories fit alongside the three Must stories in one sprint, this plan
  ships the minimum coherent Epic A slice first and holds the extensions for a follow-up once real
  usage/capacity is known, mirroring the backlog's own logic for RAV-008 ("re-evaluate for real tenant
  demand once Epic A ships and gets feedback," applied here one level up as a sprint-sizing decision,
  not a story-priority one). If the Tech Lead's ticket breakdown finds RAV-004/005 trivially cheap given
  RAV-002/003's actual implementation, flag that back to this PM role rather than silently pulling them
  in — sprint scope changes go through the same approval path as sprint creation.
- **RAV-006, RAV-007, RAV-008 (Could)** — NOT sequenced into implementation in any sprint yet. These are
  explicitly gated, per the backlog's own text, on a storage-growth sizing conversation (rows = tenants
  × runs × splits × test-window-length × baselines-per-split) that has not happened. This is an open
  architectural question for the user/Architect, not a scheduling gap — same treatment this pipeline
  already gave DBOPT-008. Do not schedule RAV-006/007/008 into a sprint until that sizing conversation
  concludes and produces an explicit go/no-go plus a retention/pruning policy, both of which RAV-006's
  own acceptance criteria already require before its implementation can start.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

All three in-scope stories are pure `services/dashboard-web` presentation work against
`gateway-api`/`validation-service` contracts that already exist and are already fired (triggers #3, #5,
#8 all long since satisfied). No new trigger is crossed, no `libs/naive_first_engine` or
`libs/common` change is required, and no service-boundary rule is at risk (dashboard-web calls
`gateway-api`'s existing public contract only, per CLAUDE.md's "no service imports another service's
code" rule — unchanged by this sprint).

## File-overlap / concurrent-work risk (flagged, not silently ignored)

`docs/sprints/sprint-24.md` (DASH-116/117/118 — crawl lifecycle dashboard controls) was **sequenced but
has not been implemented**: no `DASH-116`/`DASH-117`/`DASH-118` ticket files exist under `docs/tickets/`,
`docs/tickets/README.md` has no Sprint 24 outcome section, and `services/dashboard-web/README.md`'s
status text does not mention it. Treat it as still queued, not done. Checked for overlap: Sprint 24's
scope touches `services/dashboard-web/src/app/templates/_crawl_status_panel.html` and `monitoring.html`
(and the corresponding `gateway-api`/`ingestion-service` proxy chain) — none of which this sprint's
RAV-001/002/003 touch (`run_detail.html`, `runs_list.html` is untouched too this sprint, and
`style.css`'s existing status-neutral palette variables are read, not redefined). File overlap risk
between the two sprints is low today. The Tech Lead should still confirm, before starting Sprint 26
tickets, whether Sprint 24 is being executed concurrently by another session — if so, avoid touching
`services/dashboard-web/README.md`'s shared status header and `pyproject.toml`/test-suite files in the
same window without a rebase check, per this repo's established same-file-collision-avoidance
discipline (Sprint 14's GW-016/GW-018, Sprint 17's GW-014 precedent).

## Definition of done for this sprint

- RAV-001's decision is written down (ADR or a dated `services/dashboard-web/README.md` section) and
  explicitly answers all four of its own acceptance criteria (chosen approach, new-dependency
  disclosure, Jinja2/HTMX-compatibility confirmation, silence on Epic B).
- RAV-002 and RAV-003 both fully implemented per their acceptance criteria, including: zero-split runs
  render the existing "no results yet" message with no broken/empty chart; the existing per-split table
  remains unchanged and present; no green/red bull-bear color pairing anywhere in either chart; a
  `null`-DM split renders as its own "undefined for this split" category in RAV-003, never dropped or
  coerced; no chart/copy anywhere implies a forecast, prediction, or trading recommendation (audit
  language only, matching `run_detail.html`'s existing docstring vocabulary).
- Tests specified in RAV-002/RAV-003's own acceptance criteria pass against fixture split sets,
  including the explicit null-DM-split fixture case.
- `services/dashboard-web/README.md` updated to describe the new charts, the RAV-001 decision, and any
  new static asset/dependency introduced.
- Full `services/dashboard-web` test suite re-run with zero regressions.
- `docs/product/backlog-run-analysis-visualization.md`'s RAV-001/002/003 entries marked done with their
  acceptance-criteria boxes checked; RAV-004/005/009/010 left at their current priority/status with a
  note pointing at this sprint file's deferral reasoning; RAV-006/007/008 left explicitly flagged as
  blocked on the storage-sizing conversation, not marked todo-in-a-sprint.
