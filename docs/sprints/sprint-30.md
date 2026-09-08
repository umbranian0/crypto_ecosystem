# Sprint 30 — Dataset repair/validation helpers and horizon/parameter suggestion helpers (dashboard-web / validation-service / ingestion-service)

Sprint goal: a tenant submitting a run gets disclosed (never silent) dataset-quality handling —
reordering, exact-duplicate rows, and same-timestamp conflicts — plus a hard stop on zero-split
configurations and a clear statement of what the Horizon field's unit actually means for their
selected dataset, closing the highest-value Must-priority gaps in Epic A/B of this backlog before
any of the Should/Could suggestion tooling is built.

Backlog source: `docs/product/backlog-dataset-helpers.md` (DH-001 through DH-008; DH-090/091/092 are
Won't-fix, not scheduled).

## Scope decision

This backlog has no blocking architecture-decision gate — unlike MDF (see Sprint 31), every DH story
extends an existing, already-built module (`validation-service`'s `dataset_source.py`, `runs.py`;
`dashboard-web`'s `run_new.html`; `ingestion-service`'s existing read path) with narrow, mechanically-
checkable behavior. No ADR is required before ticketing. This sprint pulls the backlog's own stated
highest-value slice: all four `Must` stories plus DH-002 (`Should`), because DH-002 sits directly in
the middle of the DH-001→DH-002→DH-003 dependency chain the backlog itself calls out and cannot be
skipped without also skipping DH-003.

**In scope (5 stories):** DH-001, DH-002, DH-003, DH-005, DH-008.
**Deferred (see below):** DH-004, DH-006, DH-007.

## Stories in scope, in execution order

1. **DH-005** — Reject a configuration that produces zero splits [Must]. No dependency on anything
   else in this backlog. Sequenced first per the backlog's own sequencing note: cheapest correct fix,
   reuses `create_run`'s already-computed `split_count`, closes a real "completed, 0 splits" gap on
   its own with no shared-file risk against the DH-001→003 chain.
2. **DH-008** — Surface sampling interval / horizon-unit meaning on the run-submission form [Must].
   No dependency on anything else in this backlog (may optionally reuse DH-004's future gap-report
   metadata but does not require it). Sequenced second: presentation-only, no backend change, no file
   overlap with DH-005 or the DH-001→003 chain (touches `run_new.html`'s Horizon-field hint/tooltip
   only) — can run fully in parallel with DH-005 if the Tech Lead prefers, but listed second here as
   the other zero-dependency "cheap, correct" fix the backlog explicitly asks to ship alongside DH-005.
3. **DH-001** — Disclose the already-happening sort-on-load [Must]. No dependency. Sequenced third:
   first of the `dataset_source.py` chain, establishes the additive warnings-plumbing shape
   (`RunDetailResponse` warnings field, run-detail page rendering) that DH-002 explicitly depends on.
4. **DH-002** — Detect and disclose exact full-row duplicate timestamps [Should]. Depends on DH-001
   (shares its warnings-plumbing change). Sequenced fourth, immediately after DH-001, per the backlog's
   own note that DH-001→002→003 form a natural sequence inside `dataset_source.py`.
5. **DH-003** — Detect and block same-timestamp-different-value conflicts [Must]. Depends on DH-002
   (its check runs after DH-002's dedup, on the deduped series). Sequenced last: the hard-block step
   that only makes sense once DH-002's exact-duplicate dedup has already run.

## Stories explicitly deferred

- **DH-004** (`Could`) — Gap/frequency-consistency report, new `ingestion-service` read-only endpoint
  plus a `dashboard-web` display addition. Deferred: `Could` priority, no dependency pulling it into
  this sprint's Must-chain, and it's a materially separate surface (new endpoint) from the
  `dataset_source.py`/`run_new.html` work already in scope. Candidate for the sprint that also picks
  up DH-006/007.
- **DH-006** (`Should`) — Suggested train/test/step values, `computeSuggestedParameters()` in
  `run_new.html`. Deferred out of this sprint on capacity grounds (no team size/velocity given —
  see note below) even though it has no blocking dependency beyond already-shipped RSS-001/002. The
  backlog itself recommends DH-006 ship *after* DH-005 "so the suggestion helper and the zero-split
  guardrail agree on the same lower bound" — DH-005 is in this sprint, so DH-006 is correctly
  sequenced to start next, not this sprint.
- **DH-007** (`Could`) — Exact row count under a narrowed date range for DH-006's suggestion.
  Depends on DH-006 (not in this sprint) and RSS-003 (status not confirmed in the material read for
  this plan — flag to Tech Lead to confirm RSS-003's status before ticketing DH-007 in any future
  sprint). Deferred with DH-006.
- **DH-090/091/092** — Won't-fix, already decided in the backlog itself. Not scheduled, ever, absent
  a new product decision reopening them.

**Why DH-006/007/004 aren't pulled in alongside the five Must/should-chain stories:** no team size or
velocity figure was given for this planning pass. Rather than guess a story-point capacity, this plan
takes the backlog's own explicit sequencing logic (DH-005 before DH-006; DH-001→002→003 as one
indivisible chain) as the boundary of "the minimum coherent, dependency-correct slice" and stops
there. If the requester confirms team capacity supports more, DH-006 has no blocking dependency on
anything else in this sprint and could be added.

## Dependency/sequencing note (module boundaries, implementation-plan.md sections 2 and 6)

All five in-scope stories are within already-fired triggers: `validation-service` (#3) and
`dashboard-web` (#8) are both live and already own the exact files each story touches
(`dataset_source.py`, `runs.py::create_run`, `run_new.html`, `run_detail.html`,
`RunDetailResponse`). No `libs/naive_first_engine` change is in scope for any DH story — the backlog's
own out-of-scope section explicitly rules out touching `generate_splits`'s math or contract, and every
story here operates strictly before that function is called. No new service, no new trigger crossed.
`ingestion-service`'s stored-dataset path is explicitly out of scope for DH-001/002/003 (finding #1 in
the backlog: the DB's `(tenant_id, source, event_time)` key already prevents the problem those stories
detect, for that path only) — confirm the Tech Lead's ticket breakdown doesn't accidentally add
redundant checks there.

## File-overlap / concurrent-work risk

- `services/validation-service/src/app/dataset_source.py` — touched by DH-001, DH-002, DH-003 in
  strict sequence (each depends on the prior's change to the same file/return shape). Do not
  parallelize these three; assign to one implementer or hand off serially.
- `services/validation-service/src/app/routers/runs.py` (`create_run`) — touched by DH-005 (new
  `== 0` guardrail branch) and indirectly by DH-001/002/003 (surfacing `warnings`/`DatasetSourceError`
  on `RunDetailResponse`). DH-005's change is additive and independent of the DH-001→003 chain's own
  `RunDetailResponse` field addition — low collision risk, but both land in the same file; confirm
  merge order before both are in flight simultaneously.
- `services/dashboard-web/src/app/templates/run_new.html` — touched by DH-005 (new zero-split
  `computeEstimatedSplits()` rendered state) and DH-008 (Horizon-field hint/tooltip). Different
  regions of the same file (split-estimate status block vs. Horizon-field hint) — low risk, but both
  should confirm against the current committed state of `run_new.html` before starting, given this
  repo's recent history of uncommitted cross-sprint edits to shared dashboard-web templates (see
  Sprint 26/27/28's own file-overlap notes for the same file family).
- `services/dashboard-web/src/app/templates/run_detail.html` — touched by DH-001/002/003's warning
  rendering only. No other in-scope story touches this file this sprint.
- `docs/tickets/README.md` shows current uncommitted work on `dashboard-web/src/app/routers/operator.py`,
  `runs.py`, `_crawl_status_panel.html`, `run_detail.html` (crawl cancellation/progress work, per git
  status). **The Tech Lead must confirm that work is committed (or explicitly reconciled) before
  starting DH-001/002/003/005, both of which also touch `run_detail.html`/`runs.py`** — same discipline
  this repo's prior sprints (27, 28) already applied to overlapping in-flight dashboard-web work.

## Definition of done for this sprint

- DH-005: `create_run` rejects `split_count == 0` with a `422` naming the concrete cause where
  derivable; a test proves both the `0` and `> MAX_SPLIT_COUNT` boundaries fire independently and
  correctly; `run_new.html`'s live estimator renders a distinct zero-split warning state.
- DH-008: Horizon-field hint states the selected stored dataset's sampling interval and restates
  `horizon`'s meaning in that unit; tooltip updated for the no-dataset-selected case too; a plain-text
  pointer to `/runs/horizon-summary` present; no claim about which horizon is "better."
- DH-001: `_build_series` (and `ObjectStorageDatasetSource`, reusing it) detects and reports
  reordering via an additive return-shape change; `RunDetailResponse`/run-detail page surface it as a
  non-fatal warning; no change to the sort behavior itself.
- DH-002: exact full-row duplicates are dropped (first occurrence kept) and disclosed with a count;
  scoped to `InlineOrLocalFileDatasetSource`/`ObjectStorageDatasetSource` only; post-dedup row count
  feeds DH-005's zero-split check, not the pre-dedup count.
- DH-003: a same-timestamp-different-value conflict after DH-002's dedup raises `DatasetSourceError`
  naming the timestamp and both values, surfaced as `status="failed"` via the existing exception path
  — never auto-resolved; a test covers both the conflict case and the exact-duplicate case reaching
  DH-002 instead.
- Banned-word/positioning discipline unaffected — no story in this sprint touches result-framing copy
  (that's MDF-005's territory, not this sprint's).
- `services/validation-service/README.md` and `services/dashboard-web/README.md` updated for each
  story's new behavior/contract as part of the same ticket that ships it, not a separate pass.
- Full `services/validation-service` and `services/dashboard-web` test suites re-run with zero
  regressions.
- `docs/product/backlog-dataset-helpers.md`'s DH-001/002/003/005/008 entries marked done with
  acceptance-criteria boxes checked; DH-004/006/007 left unchanged, noted here as "next."

## Outcome

All five in-scope tickets (DH-005, DH-008, DH-001, DH-002, DH-003) shipped, in the sprint's stated
order, one dev agent per ticket, verified by the Tech Lead against the actual diff (not just each
dev agent's own self-report) before the next ticket started. DH-005/DH-008 landed first (both touch
`run_new.html`, different regions, sequenced rather than parallelized to avoid a same-file clobber);
DH-001->DH-002->DH-003 then ran strictly sequentially inside `dataset_source.py`, exactly as the
sprint's file-overlap note required.

**What got built**:
- `services/validation-service/src/app/routers/runs.py`: `create_run` rejects `split_count == 0` with
  a `422` naming the derived cause (DH-005), alongside the pre-existing RSS-004 `> MAX_SPLIT_COUNT`
  check.
- `services/validation-service/src/app/dataset_source.py`: `DatasetSource.load()` returns a new
  `LoadedSeries(series, warnings)` uniformly across all four implementations. `_build_series` now, in
  order: discloses a non-monotonic input via a warning (DH-001, no change to the sort itself), drops
  exact `(timestamp, value)` duplicates first-occurrence-kept and discloses the count (DH-002, scoped
  to the two non-stored `DatasetSource`s only), then hard-fails with `DatasetSourceError` naming the
  timestamp and all differing values if a genuine conflict remains post-dedup (DH-003, never
  auto-resolved).
- New migration `services/validation-service/migrations/versions/0008_add_runs_warnings_column.py`
  (`runs.warnings`, JSON, `server_default='[]'`) persists the load's warnings across the
  `POST /runs` -> `GET /runs/{id}` boundary.
- `libs/common/src/naive_first_common/contracts.py`: `RunDetailResponse.warnings` (additive, defaulted
  — confirmed safe against `gateway-api`'s and `dashboard-web`'s existing
  `RunDetailResponse(**json)` reconstruction call sites). `RunSummaryResponse` (the `GET /runs` list
  shape) deliberately not extended, matching its own documented "strict subset" precedent.
  `services/dashboard-web/src/app/templates/run_detail.html` renders `run.warnings`;
  `run_new.html` gained the DH-005 zero-split estimator state and the DH-008 Horizon-field
  sampling-interval hint (citing ADR-0007, with a reciprocal pointer to `/runs/horizon-summary`).
- One incidental fix: `services/gateway-api/tests/test_runs_routing.py`'s
  `test_get_run_forwards_and_returns_full_detail_shape` needed its literal expected-key-set assertion
  updated for the new additive `warnings` field — found and fixed by the Tech Lead during verification,
  not left for QA to catch.

**Test suites re-run clean by the Tech Lead** (not just the dev agents' own reports):
`services/validation-service` 163 passed / 1 skipped, `services/dashboard-web` 244 passed / 7
deselected (pre-existing e2e-marked exclusions), `services/gateway-api` 173 passed, `libs/common` 30
passed. `libs/naive_first_engine` untouched (out of scope for every DH story per the sprint's own
scope decision) and not re-run.

**QA gate**: run (see `qa` subagent report, 2026-09-08). Verdict: **GO**. QA independently
reproduced all five stories against `validation-service`'s real FastAPI app via `TestClient` +
real SQLite-backed repositories (not mocked at the repository-interface level) — non-monotonic input
-> disclosed warning; exact-duplicate row -> disclosed drop (QA added one new end-to-end test,
`test_qa_exact_duplicate_dataset_persists_dedup_warning_and_drops_row_end_to_end`, closing a gap where
DH-002 only had unit-level coverage of the persistence round trip); same-timestamp-conflict ->
`status="failed"` naming both values; zero-split config -> `422`; Horizon hint copy read directly and
confirmed free of positioning violations. QA also confirmed by reading the code that the dedup/conflict
checks run once, before any split boundary is computed — no per-split or future-information leakage
risk. One documentation-hygiene defect was found (this sprint's own `docs/tickets/DH-003.md` and
`docs/tickets/README.md` had not been updated to `done` despite the code, tests, and backlog file all
being correct) — fixed directly by the Tech Lead post-QA (see below), not re-delegated, since it was a
pure status-line/checkbox sync with zero code risk. No live `naive-first-validation-service`/
`dashboard-web` containers were reachable in this environment (only Postgres/Redis were up) — QA
disclosed this rather than fabricating a container-level reproduction; TestClient-level, real-database
-backed integration tests were judged sufficient verification for this sprint's scope (feature/guardrail
work, not a bug-fix ticket on a previously-broken live-traffic path).

**Deviations from plan**: none in scope or sequencing. The one process deviation was catching and
fixing, post-hoc, that the DH-003 dev agent's own summary claimed ticket-file/index updates it had not
actually made — corrected by the Tech Lead directly after QA's finding, all `docs/tickets/DH-003.md`
Implementation/Test/Documentation boxes and the ticket index's DH-001/002/003/005/008 rows now
correctly read `done`.
