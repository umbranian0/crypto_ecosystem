# Sprint 44 — services/ingestion-service, cancelled-crawl watermark bug fix

Sprint goal: a restarted crawl for a previously-cancelled `(tenant_id, source)` resolves its `since`
watermark from the real last-covered event-time, not wall-clock `fetched_at`, so no historical gap is
silently skipped — proven on a genuinely rebuilt/redeployed live stack, not merely on paper.

Backlog source: `docs/product/backlog-crawl-lifecycle-control.md` (see "One real, disclosed gap").

## Correction to ticket status (read before doing anything else)

`docs/tickets/INGEST-028.md` already exists, fully specified (Analysis, Design, and all four
acceptance-criteria sections), and every checkbox in it is currently marked done, with `Status: done`
at the top of the file. **This is false and must be corrected before this sprint starts real work.**
Independent verification (grep across `services/ingestion-service`) confirms no `latest_event_time`
method exists anywhere in that service's code today — `ConnectorRecordRepository`, its Postgres and
fake implementations, and `connectors/base.py::latest_watermark_from_db` are all still exactly as the
ticket's own "before" description states. The ticket file's Analysis and Design sections are sound
(root cause correctly traced, chosen fix correctly reasoned against the rejected alternative, no
migration needed since the existing composite primary keys already give an index-only scan) and should
be reused as-is — they are not being redone. But:

- `docs/tickets/INGEST-028.md`'s top-level `Status:` must be changed from `done` to `in progress`.
- All four acceptance-criteria sections (Implementation, Test, Review, Documentation) must have every
  `[x]` reset to `[ ]` until the Tech Lead genuinely implements, tests, and live-verifies each one —
  the current checkmarks describe work that was never actually done, including the required live-stack
  before/after reproduction.
- `docs/tickets/README.md` has no `services/ingestion-service (INGEST-028)` row at all, in the Sprint 20
  section or anywhere else — confirmed by grep, zero matches for "INGEST-028" in that file and in every
  `docs/sprints/*.md`. A row for INGEST-028 under Sprint 44 needs to be added to that index as part of
  this sprint's own documentation acceptance criteria (already stated inside the ticket file itself,
  Documentation section) — this sprint plan does not duplicate or renumber the ticket, it schedules and
  tracks the one that already exists.

This is a small, already-scoped bug fix — the sprint's sole scope is this one ticket, reusing its
existing ID and Analysis/Design content. No new stories are introduced and no backlog re-prioritization
is implied by this sprint.

## Stories in scope, in execution order

1. **INGEST-028** — Fix cancelled-crawl watermark resolution to use real event-time, not `fetched_at`
   (`services/ingestion-service` only: `repositories/interfaces.py`, `postgres_repository.py`,
   `connectors/base.py`, `tests/fake_repository.py`). No dependency — single-ticket sprint, no
   sequencing decision to make. Module-boundary check: this touches only `services/ingestion-service`,
   no `libs/naive_first_engine` or other service, so implementation-plan.md's build-order/trigger
   constraints are not implicated.

## Stories explicitly deferred

None — this sprint's scope is exactly one ticket, per the requester's explicit scoping instruction
("this one ticket as the next sprint's sole scope... a small, scoped bug fix, not a redesign").

Two items the ticket's own Documentation acceptance criteria flag as real but explicitly out of this
ticket's scope (carried here for visibility, not as sprint scope):
- A follow-up note near `docs/product/backlog-db-optimization.md`'s `DBOPT-007` entry, disclosing that
  migration `0006`'s three `fetched_at`-indexes become unused by this fix's new query (not a
  recommendation to drop them — DBA-backlog work).
- Nothing else — the ticket's own Non-goal statement (no `crawl_runs` schema change, no change to
  `record_crawl_run`/`record_crawl_progress`, no change to any connector's `fetch()` cancellation
  checkpoint logic) already scopes this correctly; nothing further needs deferring out of it.

## Definition of done for this sprint

- `docs/tickets/INGEST-028.md`'s `Status:` reset to `in progress` at sprint start (before any code is
  touched), then updated to `done` only after every item below is genuinely true and personally
  verified by the Tech Lead against the real diff — not restored to `[x]` by copying the pre-existing
  (false) checkboxes.
- `latest_event_time(tenant_id, source) -> datetime | None` added to `ConnectorRecordRepository`
  (Protocol), `PostgresConnectorRecordRepository` (via the existing `_TABLE_SPECS` tuple), and
  `FakeConnectorRecordRepository` (via `_FAKE_TABLE_SPECS`) — no fourth hand-typed table list in any of
  the three. `latest_fetched_at` unchanged on all three surfaces (not removed, not repurposed).
- `connectors/base.py::latest_watermark_from_db` calls `latest_event_time`, not `latest_fetched_at`; no
  signature change; `run_incremental` and `app/routers/connectors.py::run_connector` need no further
  change.
- No migration added (the ticket's own Design section already establishes why none is needed).
- Unit regression test proving `latest_watermark_from_db` resolves from event-time, not a divergent
  `fetched_at`, plus existing `tests/test_base.py` tests updated to use each fake record's real
  event-time column. Full `services/ingestion-service` suite re-run, zero regressions, count personally
  confirmed by the Tech Lead (not taken from a dev agent's self-report).
- **Real live-stack reproduction of the bug before the fix, and real live-stack proof of the fix after
  it**, against the actual `naive-first-ingestion-service` container (per this repo's standing "real
  containers, not a stale host-run SQLite copy" convention) — both required, not substituted with a
  mocked-repository test. This is the ticket's own stated Test and Review acceptance criteria and is
  non-negotiable given the prior false "done" status; a rebuild/redeploy step (`docker compose build` +
  `up -d --force-recreate` for `ingestion-service`) is expected before the after-fix reproduction.
- `services/ingestion-service/README.md` updated to describe `latest_event_time` as the real watermark
  mechanism, with `latest_fetched_at` explicitly retained as a separate, still-valid concept.
- `docs/tickets/README.md` gains a `services/ingestion-service (INGEST-028)` row (new subsection or
  appended to the existing INGEST-* section) pointing at this sprint and this ticket, with status
  reflecting the genuine outcome.
- QA gate: per this project's standing rule, raise the `qa` agent after the Tech Lead has verified
  INGEST-028 done, before production sign-off — this fixes a real, previously-shipped data-loss bug on
  a live code path, not documentation-only work.
