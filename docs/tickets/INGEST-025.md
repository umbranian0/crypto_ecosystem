# INGEST-025 — Binance connector: per-page progress checkpoints

Sprint: docs/sprints/sprint-23.md. Backlog: docs/product/backlog-crawl-lifecycle-control.md.
Status: **done** (scoped verification complete; full-suite re-confirmation performed once alongside
INGEST-026/027 to avoid concurrent-migration-test DB lock contention, see this sprint's index note)
Depends on: INGEST-022 (fetch-loop shape), INGEST-024 (`record_crawl_progress` write-back method + the
`on_progress` wiring in `_execute_crawl`).

## Analysis

Covers the backlog's INGEST-025 story. `BinancePriceConnector.fetch`'s pagination loop and
`on_progress` parameter already exist in shape after INGEST-022/024 — this ticket's own scope is
narrowly the callback actually being invoked with the right cumulative count, at the right point, and
`_execute_crawl` wiring it to `record_crawl_progress`. Binance/BTC price is the platform's core dataset
(`docs/da-tese-ao-produto.md`'s own thesis scope) — highest-value, lowest-risk progress story of the
three connectors.

## Design

**File touched**: `services/ingestion-service/connectors/binance_price.py` only. If INGEST-022 already
added the `on_progress` call at the correct point (per that ticket's own Design section, which already
specifies "after appending a batch's rows, before requesting the next page, cumulative count"), this
ticket's own AC may already be satisfied by INGEST-022's diff — **confirm this by reading the actual
merged `binance_price.py` before writing any new code**, and if so, this ticket's remaining scope is
purely the test (below) proving the cumulative-count contract, not a second code change duplicating
INGEST-022's own edit.

**DRY check**: reuses the exact same loop-modification point INGEST-022 already added for
`should_cancel` — one `while` loop, two optional callbacks at one call site, not two separately
threaded loops.

## Implementation acceptance criteria

- [x] `BinancePriceConnector.fetch`'s pagination loop calls `on_progress(len(all_rows))` once per page,
      immediately after that page's rows are appended to `all_rows` — a cumulative count, not a
      per-page delta. (Confirmed already correct as merged by INGEST-022 — no code change needed.)
- [x] `_execute_crawl` (already wired by INGEST-024) passes `on_progress=lambda n:
      repository.record_crawl_progress(tenant_id, connector.name, n)` at its `connector.fetch(...)` call
      site — confirm this wiring is present and correctly scoped to Binance's own crawl (no cross-tenant
      or cross-source leakage of the closure's captured variables). (Confirmed already correct as merged
      by INGEST-024 — no code change needed.)

## Test acceptance criteria

- [x] `tests/test_binance_price.py`: a fake multi-page response sequence (e.g. 3 pages of
      `MAX_KLINES_PER_REQUEST` rows each, then a shorter final page) proves `on_progress` is called once
      per page with a monotonically increasing cumulative row count (not per-page counts, not called out
      of order). (`test_on_progress_called_once_per_page_with_cumulative_count`)
- [x] A test proves `on_progress` is **not called at all** when the source has no new rows since `since`
      (an empty first-page response) — no fabricated "0 rows fetched" progress event for a crawl that
      found nothing to do. (`test_on_progress_not_called_when_no_new_rows`)
- [x] An integration-level test (extending `tests/test_connectors_router.py`'s existing
      `_execute_crawl`-triggering pattern) proves a real multi-page fake Binance crawl results in
      `record_crawl_progress` being called against the `FakeConnectorRecordRepository`, and the
      resulting `"running"` row (per INGEST-024's update-in-place semantics) ends with the correct final
      cumulative count before the terminal `"completed"` row is written.
      (`test_multi_page_binance_crawl_reports_progress_before_completion`)

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the actual diff/merged code: confirmed `on_progress(len(all_rows))` is a cumulative total, not
      a per-page delta.
- [x] Confirmed no double-counting: called exactly once per page (loop-level, not row-level).
- [x] Scoped re-run (`tests/test_binance_price.py tests/test_connectors_router.py`): `41 passed`, 0
      failed. **Isolated full-suite re-run performed by the Tech Lead after INGEST-026/027 both landed,
      with no other process touching the DB concurrently: `142 passed, 1 skipped, 0 failed`** —
      definitively confirming the earlier deadlocks were transient cross-agent contention, not a real
      regression. Full-suite re-run deferred until INGEST-026/027 (running concurrently against the same
      live Postgres container) finish, to avoid real DDL lock contention on shared migration-integration
      tests
      (observed live: concurrent `alembic upgrade head`-driven tests across parallel dev-agent sessions
      produced transient `psycopg.errors.DeadlockDetected` on `ALTER TABLE ingestion.crawl_runs`, not a
      code regression — see this sprint's cross-cutting note). Full-suite result recorded once all three
      parallel tickets have landed.

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md`'s Binance connector description gains a short note: "reports
      cumulative rows-fetched-so-far progress once per page during a crawl" — placed alongside the
      existing pagination/checkpoint description this connector's section already has (from INGEST-022's
      documentation work), not a duplicate paragraph. (Extended the existing
      `crawl_runs.rows_fetched_so_far` sentence in place, not a new paragraph.)
