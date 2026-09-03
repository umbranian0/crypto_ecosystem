# INGEST-024 — `POST /connectors/{source}/cancel` and `crawl_runs` progress columns

Sprint: docs/sprints/sprint-23.md. Backlog: docs/product/backlog-crawl-lifecycle-control.md.
Status: **done** — Tech Lead review + real live-Docker-Compose cancellation proof completed
(see Review acceptance criteria below).
Depends on: INGEST-021, INGEST-022, INGEST-023 (all done first).

## Analysis

Covers the backlog's INGEST-024 story — the endpoint the whole epic exists to deliver. Builds directly
on `run_connector`/`_execute_crawl` (`connectors.py`, `INGEST-008/014/015`), `CrawlRegistry.request_cancel`/
`should_cancel` (`INGEST-023`), `FetchResult.cancelled` (`INGEST-022`), and the `"running"` status write
(`INGEST-021`). No `naive_first_engine`/dataset-shape change (ADR-0005 unaffected).

**Race condition to get right, stated explicitly** (per the backlog's own instruction): a crawl that
finishes normally after a cancel was requested but before the fetch loop ever observed
`should_cancel()==True` at a checkpoint it evaluated must resolve to `"completed"`, not `"cancelled"`.
This is why INGEST-022 added `FetchResult.cancelled` as a field the connector itself sets, rather than
having `_execute_crawl` re-query `registry.should_cancel(...)` after `fetch()` returns — the registry
flag can be `True` at that point purely because a cancel request landed *after* the connector's last (or
only) checkpoint, which must not retroactively relabel a fetch that actually ran to completion.

## Design

**Files touched** (all `services/ingestion-service/`, one module's worth of work — router + repository +
model + migration + fakes, no other service):
- `services/ingestion-service/src/app/models.py` — `CrawlRun` gains two nullable columns:
  `rows_fetched_so_far: Mapped[int | None]` (Integer) and `updated_at: Mapped[datetime | None]`
  (DateTime(timezone=True)). Both nullable (no backfill needed for pre-existing rows — this is an
  additive, backward-compatible migration per `INGEST-016`/`017`/`018`'s own precedent).
- `services/ingestion-service/migrations/versions/0008_add_crawl_runs_progress_columns.py` — new
  Alembic revision (`0008`, `down_revision="0007"` — confirm `0007` is still head via `alembic history`
  before writing this, don't assume), `ADD COLUMN` for both, Postgres-only guard matching every prior
  migration in this service (`op.get_bind().dialect.name != "postgresql": return`).
- `services/ingestion-service/src/app/repositories/interfaces.py` — `ConnectorRecordRepository` gains
  `record_crawl_progress(self, tenant_id: str, source: str, rows_fetched_so_far: int) -> None`.
  `CrawlRunSummary` gains `rows_fetched_so_far: int | None` and `updated_at: datetime | None`.
- `services/ingestion-service/src/app/repositories/postgres_repository.py`:
  - `record_crawl_run` now also sets `updated_at=utcnow()` on every insert it makes (queued/running/
    cancelling/completed/failed/cancelled alike) — `fetched_at`'s existing meaning/ordering role is
    **unchanged**; `updated_at` is a new, separate "last touched" field, not a replacement for
    `fetched_at`. `latest_crawl_run`'s existing `ORDER BY CrawlRun.fetched_at.desc()` is **not**
    changed — it already correctly orders across the queued → running → cancelling → terminal insert
    sequence, since each is written with a strictly later real-world timestamp than the one before it.
  - `record_crawl_progress` is a **new method**, semantically distinct from `record_crawl_run`: it
    **updates in place** the most recent `status="running"` row for `(tenant_id, source)` (`SELECT ...
    WHERE tenant_id=:t AND source=:s AND status='running' ORDER BY updated_at DESC LIMIT 1`, then set
    `rows_fetched_so_far`/`updated_at` and commit) rather than inserting a new row per call. This is a
    deliberate design decision, not an oversight: a Binance historical backfill can span dozens of pages
    and a Reddit crawl up to ~1000 submissions, and inserting one new `crawl_runs` row per checkpoint
    would make this table's row count scale with fetch granularity instead of with crawl count — the
    same DBA-evidenced table-growth sensitivity `INGEST-016`/`017`/`018`/`019` already treated as a real
    cost in this service. If no matching `"running"` row exists (e.g. called after the crawl already
    finished, a defensive edge case), this is a silent no-op, never a raised exception — progress
    reporting must never crash a fetch loop that is otherwise succeeding.
  - `latest_crawl_run` maps the two new columns onto `CrawlRunSummary`.
- `services/ingestion-service/src/app/routers/connectors.py`:
  - `_execute_crawl` builds two closures at its `connector.fetch(...)` call site (mirroring the shape
    `should_cancel`'s own closure already takes from `INGEST-023`): `on_progress = lambda n:
    repository.record_crawl_progress(tenant_id, connector.name, n)` and reuses the existing
    `should_cancel` closure. Both are passed to `connector.fetch(since=since, should_cancel=...,
    on_progress=...)`.
  - After `fetch()` returns, `_execute_crawl`'s terminal write uses `result.cancelled` (not a fresh
    `registry.should_cancel(...)` query) to decide `"cancelled"` vs `"completed"` on success: `status =
    "cancelled" if result.cancelled else "completed"`. The existing exception-path `"failed"` write is
    unchanged (an exception mid-fetch is still `"failed"`, never `"cancelled"`, even if a cancel was also
    requested — the two are not mutually exclusive in reality, but `"failed"` already existed as the
    exception path and this ticket does not reprioritize it).
  - New route: `POST /connectors/{source}/cancel`, tenant-authenticated (`Depends(get_tenant_context)`,
    same seam as every other route in this router). `source` is validated against the same known-source
    set `_resolve_connector` checks (build a small `_KNOWN_SOURCES` frozenset from
    `BINANCE_SOURCE_NAME`/`_ONCHAIN_FACTORIES.keys()`/`REDDIT_SOURCE_NAME` — reused, not a fourth
    hand-typed list) — unknown source is `404`, resolved before any registry/DB call, no credential
    check needed here (cancelling never calls `fetch()` or touches credentials). `registry.request_cancel(
    tenant.tenant_id, source)`: `False` → `409` ("nothing to cancel" — mirrors `run_connector`'s own
    `409` framing, inverted, per the story's own AC); `True` → write one `record_crawl_run(tenant_id,
    source, since_watermark=None, fetched_at=utcnow(), row_count=0, status="cancelling")` row (a plain
    insert, matching this router's existing insert-only convention for status-transition writes — `None`
    for `since_watermark` since this write isn't a fetch outcome) and return `202
    {"source": source, "status": "cancelling"}`.
- `services/ingestion-service/src/app/routers/datasets.py` — `ConnectorStatusResponse` gains
  `rows_fetched_so_far: int | None = None` and `updated_at: datetime | None = None`; `connector_status`
  maps them from `CrawlRunSummary`.
- `services/ingestion-service/tests/fake_repository.py` — `FakeConnectorRecordRepository.crawl_runs`
  tuples grow the two new fields (or add a parallel `self.progress_updates` list plus in-place mutation
  of the tracked tuple — Tech Lead's call at review time is whichever keeps `latest_crawl_run`'s existing
  callers working unchanged); add `record_crawl_progress`, updating the most recent `"running"` entry for
  `(tenant_id, source)` in place, mirroring the Postgres implementation's own semantics (this fake must
  behave the same way real callers rely on, not merely satisfy the Protocol's type shape).

**DRY check performed**: grepped `record_crawl_run`/`latest_crawl_run`/`CrawlRunSummary` — one write path
(`record_crawl_run`, insert-only, unchanged), one new write path (`record_crawl_progress`, update-only,
new), one read path (`latest_crawl_run`, unchanged query column, extended projection) — no second
"resolve which table" or "fetch the latest row" implementation introduced; both write paths share
`_tenant_scoped_session`.

## Implementation acceptance criteria

- [x] `crawl_runs` gains `rows_fetched_so_far` (nullable int) and `updated_at` (nullable timestamp) via
      an additive migration; no existing column removed/renamed.
- [x] `record_crawl_run` sets `updated_at` on every insert; `fetched_at`'s existing semantics/ordering
      role is unchanged.
- [x] `record_crawl_progress(tenant_id, source, rows_fetched_so_far)` updates the most recent
      `status="running"` row for that `(tenant_id, source)` in place (not a new insert); a no-op, not an
      exception, if no such row exists.
- [x] `_execute_crawl` wires `on_progress`/`should_cancel` into `connector.fetch(...)`; the terminal
      write uses `result.cancelled` to choose `"cancelled"` vs `"completed"` (exception path unchanged,
      still `"failed"`).
- [x] `POST /connectors/{source}/cancel`: `404` unknown source; `409` nothing in flight; on success,
      `registry.request_cancel(...)` + a `"cancelling"` `crawl_runs` insert + `202
      {"source", "status": "cancelling"}`.
- [x] `GET /connectors/{source}/status` response includes `rows_fetched_so_far`/`updated_at` (both
      `None`/absent-shaped for a source that never reported progress — never a fabricated `0`).
- [x] `blockchain_info_*` sources: a cancel request while the one blocking `GET` is already in flight
      still writes `"cancelling"` immediately (the registry check/write happens before `fetch()` starts,
      is honest about the *request* being received) but the row only ever resolves to `"cancelled"` if
      `BlockchainInfoConnector.fetch` itself observed `should_cancel()==True` at its one pre-request
      checkpoint (`INGEST-022`) — once the request is in flight, `fetch()` runs to natural
      completion/failure and `result.cancelled` is `False`, so the terminal write is `"completed"`
      (or `"failed"` on an exception) regardless of the pending cancel flag. This is the same
      `result.cancelled`-driven logic as Binance/Reddit — no special-cased branch for this connector in
      `_execute_crawl` itself, the honesty guarantee falls entirely out of `BlockchainInfoConnector.fetch`
      only ever setting `cancelled=True` at its one real checkpoint.

## Test acceptance criteria

- [x] `tests/test_connectors_router.py`: `test_cancel_unknown_source_returns_404`,
      `test_cancel_nothing_in_flight_returns_409`, `test_cancel_success_returns_202_and_writes_cancelling_row`.
- [x] `test_execute_crawl_race_finishes_completed_despite_pending_cancel` — non-tautological proof of the
      race condition's resolution.
- [x] `test_record_crawl_progress_updates_running_row_in_place` (`test_datasets_router.py`) — row count
      does not grow.
- [x] `test_connector_status_never_reported_progress_returns_none_not_zero` (`test_datasets_router.py`).

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the actual migration file: Postgres-only guarded, additive, `down_revision='0007'` confirmed
      correct against the real `migrations/versions/` directory listing. Live-confirmed applied:
      `ingestion.alembic_version` reads `0008` on the real container, `\d ingestion.crawl_runs` shows both
      new nullable columns.
- [x] Read `record_crawl_progress`: confirmed `UPDATE`-shaped (`SELECT ... status='running' ORDER BY
      updated_at DESC LIMIT 1` then mutate-and-commit, never an `INSERT`), correctly scoped to
      `(tenant_id, source, status='running')`.
- [x] Read `_execute_crawl`'s terminal-write logic: confirmed `result.cancelled` drives the choice; the
      documented race is unit-tested (`test_execute_crawl_race_finishes_completed_despite_pending_cancel`)
      and traced through directly in the diff.
- [x] **Live-verified against the real running Docker stack** (rebuilt `ingestion-service` with this
      ticket's code, `docker compose up -d ingestion-service`, confirmed healthy): triggered a real
      `POST /connectors/binance_price_btcusdt_1h/run` for a fresh tenant (`since=2017-08-17`, a ~9-year
      backfill), observed live progress via `GET .../status` (`rows_fetched_so_far` climbing, e.g. `12000`
      mid-flight), issued `POST .../cancel` mid-flight (`202 {"status": "cancelling"}`), and within ~5s the
      status resolved to `"cancelled"` with `row_count=23000`. Direct `psql` read of
      `ingestion.crawl_runs` (RLS bypassed via `SET row_security = off` as superuser) confirms the exact
      4-row sequence the design predicts: `queued` → `running` (updated in place to
      `rows_fetched_so_far=23000`, not re-inserted) → `cancelling` → `cancelled` (`row_count=23000`).
      Direct `psql` read of `ingestion.price_ohlcv` confirms **exactly 23000 rows** for that tenant,
      `count(*) == count(DISTINCT open_time)` (no duplicates), spanning `2017-08-17 04:00` to
      `2020-04-05 18:00` with no gap or partial/corrupt row — the crawl stopped exactly where it said it
      stopped, with no data corruption or duplication.
- [x] Full `services/ingestion-service` test suite re-run by the Tech Lead: `134 passed, 1 skipped`
      (pre-existing unrelated skip), zero regressions.

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md` updated: new `POST /connectors/{source}/cancel` section,
      `GET /connectors/{source}/status`'s section updated with the two new fields, `crawl_runs` schema
      description gains the two new columns and the update-in-place design note. Confirmed by the Tech
      Lead via grep of the actual diff.
