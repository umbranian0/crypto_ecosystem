# Sprint 40 — dashboard-web guided input + first research/ code (parallel, independent tracks)

Sprint goal: the tenant can pick an existing run from a dropdown instead of typing its id when
generating a report, and `research/` gains its first real code — a leakage-safe, per-fold-only
engineered feature set with unit tests proving no fold-boundary leakage.

Backlog source: `docs/product/backlog-guided-input.md` (GI-001), `docs/product/backlog-model-research.md`
(MR-002).

## Stories in scope, in execution order

Two independent, parallel-eligible tracks — different modules, no file overlap between them. Order
within each track is trivial (one story each); the ordering note below is only about why these two can
run concurrently, not a sequencing dependency between them.

**Track A — `services/dashboard-web`, no `research/` overlap:**
1. **GI-001** — convert `monitoring.html`'s "Generate a report" `run_id` free-text field to a `<select>`
   dropdown of the tenant's own runs, reusing `runs.py`'s existing `GET /runs` call/`RunSummaryResponse`
   parsing (no second implementation of that call — DRY rule, implementation-plan.md section 9). No
   dependency on anything in this sprint or any open story; the "Why not X" rejected fields in
   `backlog-guided-input.md` (dataset_reference_field, horizon, tenant_id, date ranges, numeric tuning
   params) are explicitly out of scope — do not fold them in.

**Track B — `research/`, no `services/dashboard-web` overlap:**
2. **MR-002** — engineered feature functions (rolling volatility, rolling mean/std of returns, lagged
   returns) in `research/features.py` (or similar), each taking only a train-fold `Series` as input, with
   a unit test per function proving no data past its own fold boundary leaks in. No dependency on
   anything in this sprint. Explicitly not a claim that these features help — MR-004/MR-005 (not in this
   sprint) answer that question via DM-test results, not this story.

**Why these two are safe to run in parallel**: GI-001 touches only `services/dashboard-web` (`monitoring.html`,
`runs.py`'s existing read path, `operator.py`'s render path). MR-002 touches only `research/` (new files) and
has no dependency on `naive_first_engine`, `validation-service`, or any `dashboard-web` template. No shared
file, no shared module boundary, no data dependency in either direction — the Tech Lead may assign these to
two dev agents concurrently with no coordination needed between them.

## Stories explicitly deferred

- **GI-001's "Why not X" rejected fields** (`dataset_reference_field`, `horizon`, `tenant_id`,
  `dataset_reference_start`/`end`, `since`, `train_window`/`test_window`/`step`/`purge_gap_hours`) — not
  deferred stories, they were never approved stories; `backlog-guided-input.md` itself already rejected
  each with a stated reason. Not in scope for this or any sprint unless a future backlog item reopens one
  (e.g. `tenant_id` is explicitly gated on `SETUP-011`-derived future work, already shipped, but that
  backlog file does not currently propose reopening it).
- **MR-001** — already done (Sprint 33, `docs/tickets/MR-001.md`), not re-scheduled here.
- **MR-003** — deferred, blocked on MDF-003 (already shipped per Sprint 36) but MR-003 itself is not
  requested in scope for this sprint; not pulled in without explicit Product Owner sequencing.
- **MR-004, MR-005, MR-006** — deferred. Per the standing "keep it simple, don't over-engineer"
  constraint and this run's explicit instruction, this sprint does not scope-creep into the candidate
  model stories (MR-004 gradient boosting, MR-005 regime-sensitive, MR-006 explainability) that MR-002
  sets up. MR-004 additionally depends on MR-001 (satisfied) and would be the natural next research
  story, but is not pulled into this sprint without a separate approval pass — light-compute/no-GPU
  constraint applies to that future story, not to MR-002 itself.

## Definition of done for this sprint

- GI-001 and MR-002's acceptance criteria (as stated in `docs/product/backlog-guided-input.md` and
  `docs/product/backlog-model-research.md` respectively) are checked off.
- Each story's own unit test(s) pass (MR-002: leakage-boundary tests per function, non-negotiable per its
  own acceptance criteria; GI-001: dropdown-render, zero-runs-fallback, transport-failure-fallback, and
  previously-submitted-value-preservation tests). Full existing suites (`services/dashboard-web`, and any
  new `research/` test runner) re-run with zero regressions.
- `services/dashboard-web/README.md` updated with GI-001's shipped status/contract note (dropdown
  behavior, fallback behavior, no `POST /monitoring/reports/generate` contract change).
- `research/README.md` updated: status moves from "greenlit, no model-class research work has begun" to
  reflect MR-002 shipped, feature functions listed, explicit note that MR-004/MR-005/MR-006 remain not
  started and are not implied by this sprint.
- `docs/product/backlog-guided-input.md`'s GI-001 entry and `docs/product/backlog-model-research.md`'s
  MR-002 entry marked done with acceptance-criteria boxes checked, pointing to their ticket file(s),
  matching prior-sprint convention.
- `docs/tickets/README.md` gains entries for the ticket(s) opened against GI-001 and MR-002, in their own
  module sections (`dashboard-web` DASH-* series and a new `research/` MR-* ticket-tracking subsection
  respectively), matching the existing table format.
- QA gate: per this platform's standing rule, the Tech Lead raises the `qa` agent (`/qa-validation`)
  after both tickets in this sprint are done, before production sign-off. GI-001 touches a rendered
  tenant-facing form (no API contract change); MR-002 touches only `research/` unit-tested pure functions
  with no service/API surface — QA scope should be sized to that (no live-deploy rebuild is needed for
  `research/`-only code, since nothing in `research/` runs inside a deployed service).

## Next (explicitly not this sprint)

- MR-004 (gradient boosting `Baseline`) is the natural next research story once MR-002 lands, subject to
  the light-compute/no-GPU/small-fast-models constraint and separate Product Owner/requester sign-off —
  not scheduled here.
- Any further `backlog-guided-input.md` work requires a new story to be added and approved by the Product
  Owner first; that backlog currently contains only GI-001.
