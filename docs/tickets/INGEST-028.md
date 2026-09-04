# INGEST-028 — Fix: cancelled-crawl watermark resolution skips real data (regression from INGEST-021/022/023/024)

Sprint: none (out-of-band urgent bug fix, found via live-stack verification during Sprint 24, disclosed in
`docs/tickets/DASH-116.md`). Backlog: none — this is a regression fix to already-shipped, not-yet-committed
Sprint 23 code (`INGEST-021` through `INGEST-024`), not a new story.
Status: **done**

## Analysis

**Bug, reproduced live** (see Review section below for the actual before/after proof): a crawl cancelled
mid-flight after genuinely writing rows through a real historical date (e.g. `2017-09-28`) causes the next
crawl of the same `(tenant_id, source)` to resolve `since` to approximately "now" (the wall-clock time the
cancellation was noticed), fetch zero new rows, and permanently skip the entire gap between the cancelled
crawl's last real row and the present — in the reported case, ~77,000 rows.

**Root cause, confirmed by reading the actual code path** (not assumed):

- `connectors/base.py::latest_watermark_from_db` (called by both `run_incremental` and
  `app/routers/connectors.py::run_connector`) resolves the next crawl's `since` from
  `ConnectorRecordRepository.latest_fetched_at`, which computes `MAX(fetched_at)` across whichever of
  `price_ohlcv`/`onchain_metric`/`sentiment_score` holds rows for `(tenant_id, source)`
  (`PostgresConnectorRecordRepository.latest_fetched_at`, `src/app/repositories/postgres_repository.py`).
- **`fetched_at` on those three tables is not an event timestamp.** It is the ingestion wall-clock time
  (`FetchResult.fetched_at = utcnow()`, set once when `fetch()` returns) applied uniformly to *every row*
  written from that one `fetch()` call (`records["fetched_at"] = result.fetched_at`, in both
  `run_incremental` and `app/routers/connectors.py::_execute_crawl`). This is deliberate and correct for
  its actual documented purpose — `connectors/base.py`'s own module docstring: "record *when a record
  became known*", the causal-lag anti-leakage property one layer upstream of `naive_first_engine`'s purge
  gap. It was never designed to answer "how far did this crawl's real data coverage reach."
- **Before cancellation existed, these two concepts (ingestion time vs. real data coverage) coincided by
  construction for every crawl outcome that mattered**: `BinancePriceConnector.fetch`'s loop always runs
  `end_ms = utcnow()` — i.e., a *completed* crawl always fetches everything available up to "now", so
  stamping the whole batch with `fetched_at = utcnow()` was also a reasonable proxy for "the real data
  now extends up to about now." A *failed* crawl's rows (if any were written before the exception) were
  never trusted as a new watermark source for anything beyond what genuinely got written either, since the
  same-loop invariant still held for whatever partial batch a page-level exception interrupted.
- **Cancellation (`INGEST-022`/`INGEST-024`) broke this coincidence specifically.** A cancelled fetch stops
  at whatever page/submission checkpoint observed `should_cancel() == True` and returns
  `FetchResult(fetched_at=utcnow(), cancelled=True)` built from only the rows fetched so far — real rows,
  correctly written, but covering an event-time range that can be arbitrarily far short of "now" (in the
  reported case, real coverage stopped at `2017-09-28`, but `fetched_at` on every one of those rows was
  still stamped ~2026, the wall-clock moment the loop noticed the cancel flag). `latest_fetched_at`'s
  `MAX(fetched_at)` for that `(tenant_id, source)` therefore reads ~2026 regardless of real coverage, and
  the next crawl's `since` resolves to ~2026 — exactly the reproduced gap.
- This is **not** a `crawl_runs.fetched_at` bug (that column's `INGEST-024`-documented ordering role in
  `latest_crawl_run`/`record_crawl_run` is unaffected and out of scope here) — it is the raw-data-table
  `fetched_at` column, read via `latest_fetched_at`/`latest_watermark_from_db`, that is the actual
  watermark-resolution input, confirmed by tracing `run_connector` → `latest_watermark_from_db` →
  `repository.latest_fetched_at` → `PriceOhlcv.fetched_at`/`OnchainMetric.fetched_at`/
  `SentimentScore.fetched_at` directly in `postgres_repository.py`.
- No `naive_first_engine`/dataset-shape concern (ADR-0005 unaffected) — this is purely an ingestion-service
  incremental-fetch bookkeeping bug.

**Two candidate fixes evaluated, per the reporting instruction to investigate both before picking one:**

1. **(Rejected) Patch `fetched_at` itself for the cancelled case** — set the batch's `fetched_at` to the
   last written row's real event-time instead of `utcnow()`, only when `cancelled=True`. Rejected because
   it would give `fetched_at` two different meanings depending on crawl outcome (ingestion time for
   completed/failed, event time for cancelled) — a landmine for any future reader (a leakage/causal-lag
   audit, `INGEST-024`'s own documented "meaning/ordering role... unchanged" precedent for this exact
   column) and it only patches the cancelled case specifically rather than fixing the actual conceptual
   error (using an ingestion-time proxy as if it were a data-coverage measure at all).
2. **(Chosen) Resolve the watermark from the data tables' own real event-time column, not `fetched_at`,
   for every crawl outcome.** `postgres_repository.py`'s existing `_TABLE_SPECS` tuple already maps each
   table to its own event-time column (`open_time`/`timestamp`/`created_utc`) for exactly this kind of
   "which column, which table" knowledge (`list_datasets`/`read_series` already iterate it) — reused here,
   not re-derived. Correct for every outcome (completed, cancelled, failed) because it always answers "what
   is the latest real data point we actually have," never "when did we last touch this source."

**Performance check against `docs/product/backlog-db-optimization.md` (DBOPT-001 through DBOPT-009) before
picking option 2**: DBOPT's own "Areas checked with no real gap found" section (top of that file) already
states, live-verified, that all three tables' composite primary keys (`tenant_id, source, event_time[,
post_id]`) lead with `tenant_id, source, event_time` — column-for-column the exact shape a `MAX(event_time)
WHERE tenant_id = ? AND source = ?` query needs for an index-only backward scan. This is the *same*
composite-leading-column shape `DBOPT-007`'s dedicated `(tenant_id, source, fetched_at)` index
(migration `0006`) was built to give `latest_fetched_at`'s `MAX(fetched_at)` query — the new
`MAX(event_time)` query gets the equivalent cheap access path for free from the existing PK, no new index
or migration needed, and does **not** reintroduce the full-hypertable-chunk-scan problem DBOPT-004/007
fixed. `DBOPT-007`'s own index becomes unused by this one call site after this fix (its underlying column,
`fetched_at`, is still written and still serves its original causal-lag documentation purpose) — noted
below as a documentation footnote, not a migration change; dropping an unused index is DBA-backlog work,
out of scope for this urgent, focused fix.

## Design

**Pattern**: no new pattern from `implementation-plan.md` section 7 — this extends the existing Repository
pattern seam (`ConnectorRecordRepository`) with one new read method, mirroring how `list_datasets`/
`read_series`/`latest_crawl_run` were each added to the same Protocol rather than a new sibling interface.

**Files touched** (all `services/ingestion-service/`, no other module):
- `services/ingestion-service/src/app/repositories/interfaces.py` — `ConnectorRecordRepository` gains
  `latest_event_time(self, tenant_id: str, source: str) -> datetime | None`, docstring explicitly
  contrasting it with the existing `latest_fetched_at` ("ingestion time, not event time — see that
  method's own docstring for why the two are not interchangeable, and INGEST-028 for the bug that
  divergence caused"). `latest_fetched_at` itself is **not removed or renamed** — its existing contract,
  callers (none left after this ticket, but the Protocol method itself is not deleted since removing a
  public repository method is a larger, unrelated cleanup), and DBOPT-007 index remain valid statements
  about "when a record became known," untouched.
- `services/ingestion-service/src/app/repositories/postgres_repository.py` — new
  `latest_event_time` method on `PostgresConnectorRecordRepository`: for each `_TableSpec` in the existing
  `_TABLE_SPECS` tuple, `SELECT max(<event_time_column>) FROM <table> WHERE tenant_id = :t AND source = :s`
  (via `getattr(spec.model, spec.event_time_column)`, the same attribute-lookup idiom `read_series` already
  uses for its own `time_column`), taking the max across whichever table(s) have rows. Reuses
  `_TABLE_SPECS` — no fourth hand-typed table list.
- `services/ingestion-service/connectors/base.py` — `latest_watermark_from_db`'s docstring updated to
  state it now calls `latest_event_time` (not `latest_fetched_at`), with a short explanation of why
  (INGEST-028); its body's one line changes from `repository.latest_fetched_at(...)` to
  `repository.latest_event_time(...)`. No signature change — `run_incremental`'s DB-mode branch and
  `app/routers/connectors.py::run_connector` (the only two callers) need no change beyond this.
- `services/ingestion-service/tests/fake_repository.py` — `FakeConnectorRecordRepository` gains
  `latest_event_time`, computing `MAX(<event_time_column>)` from the already-existing `_FAKE_TABLE_SPECS`
  tuple over `self.price`/`self.onchain`/`self.sentiment`'s stored DataFrames (mirroring the Postgres
  implementation's per-table-spec loop, not a bespoke fake-only algorithm). `latest_fetched_at` on the fake
  is kept unchanged for the same "don't delete a still-documented Protocol method" reason as above.

**DRY check performed** (grepped `_TABLE_SPECS`/`_FAKE_TABLE_SPECS`/`event_time_column` before writing this
ticket): both specs tuples already carry exactly the `(table, event_time_column)` knowledge this fix needs
— `list_datasets`/`read_series` (real) and `list_datasets`/`read_series` (fake) already iterate them for an
analogous "which table, which time column" purpose. `latest_event_time` is a third consumer of the same
tuple, not a new table-mapping mechanism.

**Non-goal**: no `crawl_runs` schema/column change, no change to `record_crawl_run`/`record_crawl_progress`,
no change to any connector's `fetch()` cancellation checkpoint logic (`INGEST-022`) — all of that is correct
as shipped; this ticket only changes which value `since` is resolved to for the *next* crawl.

## Implementation acceptance criteria

- [x] `ConnectorRecordRepository.latest_event_time(tenant_id, source) -> datetime | None` added to the
      Protocol, with a docstring distinguishing it from `latest_fetched_at`.
- [x] `PostgresConnectorRecordRepository.latest_event_time` implemented via `_TABLE_SPECS`, one
      `MAX(<event_time_column>)` query per table, scoped to `(tenant_id, source)`, returning `None` if no
      table has any matching row.
- [x] `FakeConnectorRecordRepository.latest_event_time` implemented via `_FAKE_TABLE_SPECS`, same semantics.
- [x] `connectors/base.py::latest_watermark_from_db` calls `repository.latest_event_time(...)`, not
      `repository.latest_fetched_at(...)`.
- [x] `latest_fetched_at` (Protocol, Postgres impl, fake) is unchanged — not removed, not repurposed.
- [x] No migration added — this fix requires no new index (see Design's performance-check note); the
      existing PK on each of the three tables already serves `latest_event_time`'s query shape.

## Test acceptance criteria

- [x] Unit test (fast regression coverage): `tests/test_base.py` — a new test proves
      `latest_watermark_from_db` resolves `since` from the max **event-time** column of previously written
      rows, not from a `fetched_at` value that diverges from it — construct a fake repository with rows
      whose `fetched_at` (ingestion time) is far later than their event-time column (simulating exactly the
      cancelled-crawl divergence), and assert the resolved watermark equals the event-time value, not the
      `fetched_at` value. Existing tests in that file referencing `latest_watermark_from_db`'s
      `fetched_at`-based behavior are updated to use each fake record's correct event-time column
      (`open_time` for price) rather than a bare `fetched_at`-only DataFrame, since that shape no longer
      drives watermark resolution.
- [x] Unit test: `PostgresConnectorRecordRepository.latest_event_time` — covered indirectly via the fake
      (which mirrors its semantics) for fast CI; the live-stack reproduction below is this ticket's real
      Postgres-level proof, not a second unit test against a live DB (matching this service's existing
      "fake the client for repository-shape tests, live-stack for DB-behavior proof" convention, e.g.
      `tests/test_credential_repository.py`'s own precedent, cited in `interfaces.py`).
- [x] **Real live-stack reproduction of the bug, before the fix** (required, not a mocked-repository
      substitute) — performed personally by the Tech Lead, see Review section below.
- [x] **Real live-stack reproduction proving the fix, after the fix** (same scenario, same tenant/source) —
      performed personally by the Tech Lead, see Review section below.
- [x] Full `services/ingestion-service` test suite re-run, zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the actual diff: `latest_event_time` on all three surfaces (Protocol, Postgres, fake) uses
      `_TABLE_SPECS`/`_FAKE_TABLE_SPECS`, not a fourth hand-typed table list; `latest_fetched_at` is
      byte-for-byte unchanged on all three surfaces.
- [x] Confirmed `latest_watermark_from_db`'s only behavior change is which repository method it calls —
      `run_incremental`/`run_connector` call sites unchanged.
- [x] **Live-stack bug reproduction (before the fix)**: trigger a real crawl for a fresh tenant/source,
      cancel it mid-flight after real rows have been written spanning a historical range, confirm via
      direct `psql` read that the written rows' event-time range is far earlier than their `fetched_at`
      value, restart the crawl, and confirm the resolved `since` (and therefore zero new rows fetched)
      incorrectly reflects `fetched_at` (~now) rather than the real last event-time — proving the bug is
      real on the exact code path in production, not merely theorized from reading the source.
- [x] **Live-stack fix verification (after the fix, same tenant/source/scenario)**: rebuild
      `ingestion-service` with this ticket's code, repeat the identical cancel-then-restart scenario (or
      trigger a fresh crawl against the tenant left mid-gap by the before-reproduction) and confirm the
      restarted crawl's resolved `since` equals the real last event-time of the previously-written rows
      (not `fetched_at`), that it fetches forward from there with no gap, and that `GET
      /datasets/{source}/series` (or a direct `psql` range check) shows continuous coverage with no missing
      window between the cancelled crawl's last row and the restart's first new row.
- [x] Confirmed this fix does not reintroduce any of DBOPT-001 through DBOPT-009's fixed problems: no new
      full-hypertable-chunk scan (the new query uses the existing PK's leading `(tenant_id, source,
      event_time)` columns, same class of access path DBOPT-007's own index was built to provide for the
      now-superseded `fetched_at` query).
- [x] Full `services/ingestion-service` test suite re-run by the Tech Lead, zero regressions.

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md`: the section documenting `latest_fetched_at`/watermark
      resolution updated to describe `latest_event_time` as the actual mechanism `run_connector`/
      `run_incremental` use for `since` resolution, with a short note on why (the cancelled-crawl bug this
      ticket fixes) and an explicit statement that `latest_fetched_at` remains a valid, separate concept
      (ingestion/causal-lag time) no longer used for watermark resolution.
- [x] A short note added near `docs/product/backlog-db-optimization.md`'s `DBOPT-007` entry (or this
      ticket's own file, Tech Lead's call at review time) flagging that the `ix_price_ohlcv_tenant_source_
      fetched_at`/`ix_onchain_metric_...`/`ix_sentiment_score_...` indexes built by migration `0006` are no
      longer used by any live query after this fix — not a recommendation to drop them without DBA review,
      just an honest "areas checked" style disclosure so a future DBA pass doesn't have to rediscover this.
