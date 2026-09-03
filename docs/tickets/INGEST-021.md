# INGEST-021 — `crawl_runs` status vocabulary gains `running`/`cancelling`/`cancelled`

Sprint: docs/sprints/sprint-23.md. Backlog: docs/product/backlog-crawl-lifecycle-control.md.
Status: **done**

## Analysis

Covers the backlog's INGEST-021 story in full. Today `crawl_runs.status` (a plain `String` column,
`app/models.py::CrawlRun.status`) only ever takes `"queued"`/`"completed"`/`"failed"`
(`app/routers/connectors.py::run_connector`/`_execute_crawl`). Every later story in Epic 1/2 needs
`"running"` (a crawl is actually in flight, not just accepted) and `"cancelling"`/`"cancelled"` (a stop
request was made / took effect) to write into or report against — this ticket is pure foundation, no
new capability of its own yet.

Constraint from docs: this is `ingestion-service`'s **third** disclosed extension of its
already-twice-overridden trigger #6 surface (per `docs/adr/0003-disclosed-trigger-override-pattern.md`
and the backlog's own "Trigger-override disclosure" section) — carry that framing into this ticket's own
Outcome note, not re-derive it. No change to `naive_first_engine` (ADR-0005 unaffected — this only
touches the crawl-run *event*, never what a dataset is).

## Design

No design pattern from implementation-plan.md section 7 is newly invoked here — this is a vocabulary
change to an existing plain string column (Repository pattern, already in place, is unaffected).

**Files touched** (all within `services/ingestion-service/`, no other module):
- `services/ingestion-service/src/app/routers/connectors.py` — `_execute_crawl` gains one new
  `record_crawl_run(..., status="running")` call, made immediately before the `connector.fetch(...)`
  call, using the same `since`/`connector.name` values already in scope. Use `utcnow()` (already
  imported from `connectors.base`) for both `fetched_at` and `row_count=0` on this write — it is a
  bookkeeping row, not a fetch outcome.
- `services/ingestion-service/README.md` — status vocabulary section (currently documents
  `"queued"`/`"completed"`/`"failed"` only, see the `POST /connectors/{source}/run` section) gains all
  six values and what each means.

**DRY check**: `record_crawl_run`'s signature (`tenant_id, source, since_watermark, fetched_at,
row_count, status`) already accepts any string for `status` — no interface/model change needed for this
ticket (the column is a plain `String`, not a DB enum type; `app/repositories/interfaces.py`'s
`ConnectorRecordRepository.record_crawl_run` docstring is worded generically enough that it needs no
edit). Reuses the exact same `record_crawl_run` call shape `run_connector`'s existing `"queued"` write
already uses — no second write helper introduced.

## Implementation acceptance criteria

- [x] `record_crawl_run`'s `status` parameter accepts `"running"`, `"cancelling"`, `"cancelled"` in
      addition to `"queued"`/`"completed"`/`"failed"` — true by construction (no validation/allowlist
      exists anywhere on this parameter today; confirm this by grep, don't add a new allowlist that
      would then need maintaining).
- [x] `_execute_crawl` writes a `status="running"` row immediately before calling `connector.fetch(...)`,
      not just at completion.
- [x] No migration/column-shape change in this ticket — `status` stays the existing plain `String`
      column.

## Test acceptance criteria

- [x] A unit test (extend `tests/test_connectors_router.py`, using the existing `FakeConnectorRecordRepository`
      fixture) proves: after `POST /connectors/{source}/run`'s background task runs to completion (the
      existing `TestClient`-executes-`BackgroundTasks`-synchronously behavior already documented in that
      test file), `connector_repository.crawl_runs` contains a `"running"` row (in addition to the
      existing `"queued"` and terminal rows) for that `(tenant_id, source)`, written before the terminal
      row (assert by list order or by an explicit sequence check, not just presence). New test:
      `test_running_row_written_before_terminal_row`; existing tests asserting exact `crawl_runs`
      length/order were also updated to account for the new row.

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the actual diff to `_execute_crawl`: the `"running"` write happens before `connector.fetch(...)`
      is called, not after, and does not change the existing "queued" write in `run_connector` or the
      existing terminal (`"completed"`/`"failed"`) write at the end of `_execute_crawl`. Confirmed.
- [x] Confirm no other file under `services/ingestion-service/` needed a change for this ticket (`git
      status` scoped to the module shows only `connectors.py` + `README.md` + the new/edited test file).
      Confirmed via `git diff --stat`.
- [x] Full `services/ingestion-service` test suite re-run, zero regressions. Tech-Lead-re-run: `115
      passed, 1 skipped` (pre-existing, unrelated skip).

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md`'s `POST /connectors/{source}/run`/status section lists all
      six values (`queued`, `running`, `cancelling`, `cancelled`, `completed`, `failed`) and what each
      means, replacing the current three-value description.
