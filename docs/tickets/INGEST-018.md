# INGEST-018 — Three ingestion hypertables: composite index on `(tenant_id, source, fetched_at)`

**Sprint**: 21. **Module**: `services/ingestion-service`. **Status**: done. **Depends on**: INGEST-017
(same service, shares the linear Alembic migration chain — run strictly after INGEST-017's revision
lands; complementary to, not blocked by, INGEST-016's chunk-interval fix on the same three tables per
the PM's sprint plan).

**Tech Lead verification (2026-09-02)**: this ticket's dev agent was cut off mid-session (usage-limit
interruption) after completing the migration and test files but before finishing the live-verification
pass, the README documentation addition, and its own Outcome writeup. Checked current on-disk state
before redoing anything: `migrations/versions/0006_add_hypertables_tenant_source_fetched_at_index.py`
and `tests/test_hypertable_tenant_source_fetched_at_index_migration.py` were both already complete and
correct on read — three `CREATE INDEX` statements (fetched_at trailing), Postgres-guarded, `revision =
"0006"`/`down_revision = "0005"` correctly chaining onto `INGEST-017`'s head, a clean `downgrade()`, and
a well-built test file (index-existence + chunk-propagation + round-trip, all skip-guarded on real-
Postgres reachability, explicitly re-verifying — not assuming — `VS-026`'s propagation finding for this
service's own hypertables). Completed the remaining work directly rather than re-delegating: ran the
full test suite, performed the live verification, added the README note, and wrote this Outcome section.

**Test suite**: `.venv/Scripts/python.exe -m pytest tests/ -q` — **108 passed, 1 skipped** (the
`sentiment_score` chunk-propagation case skips because that table has zero rows/chunks this session, per
the test's own explicit skip message — not a failure), 0 regressions from `INGEST-017`'s 102-passed
baseline (102 + 7 new INGEST-018 tests, one of which is the disclosed skip).

**Live verification against the real running `naive-first-postgres` container**: `ingestion.alembic_
version` is `0006`. `pg_indexes` confirms all three indexes exist on their hypertable roots
(`ix_price_ohlcv_tenant_source_fetched_at`, `ix_onchain_metric_tenant_source_fetched_at`,
`ix_sentiment_score_tenant_source_fetched_at`), each `(tenant_id, source, fetched_at)` with `fetched_at`
trailing as designed.

*Chunk-propagation proof* (querying `timescaledb_information.chunks` joined against `pg_indexes` on the
real chunk relation names, same method `VS-026` used): **`price_ohlcv`: 472/472** existing chunks carry
the propagated index; **`onchain_metric`: 922/922`** existing chunks carry it. (`sentiment_score` has
zero existing chunks this session, consistent with its 0-row count — nothing to propagate to yet.)

*Live `EXPLAIN (ANALYZE, BUFFERS)`*, before (`alembic downgrade 0005`) vs. after (`alembic upgrade
head`), on the DBA's exact query shape:

- **`price_ohlcv`**, real tenant with 79,127 rows (`binance_price_btcusdt_1h`) — *before*: `Finalize
  Aggregate` over a 472-chunk `Append` of `Seq Scan`s, `Planning Time: 619.9 ms`, `Execution Time: 85.1
  ms` (matches the DBA's originally-reported shape). *After*: `Merge Append` of per-chunk `Index Only
  Scan Backward using <chunk>_ix_price_ohlcv_tenant_source_fetched_at`, one row pulled per relevant
  chunk instead of a full per-chunk aggregate — `Buffers: shared hit=472` (vs. the DBA's originally
  measured `shared hit=2907`), a real reduction in buffer touches and a structurally cheaper access
  path per chunk.
- **`onchain_metric`**, real tenant with 6,439 rows (`blockchain_info_hash-rate`) — after migration:
  same `Index Only Scan Backward` pattern confirmed live.

**Honest caveat, consistent with this sprint's `VS-026`/`INGEST-016` findings, not glossed over**:
`onchain_metric`'s own Planning Time (`1506.6 ms` in this session's live run) remains high and is **not**
fixed by this index — it is driven by the sheer chunk count (922), the same chunk-count-driven planning
cost `INGEST-016`'s chunk-interval retuning targets for *future* chunks, not by whether each chunk has
a supporting index. This ticket's own value is exactly what its Design section states: turning each
chunk's own scan from a full sequential aggregate into a cheap index-only lookup (a real, measured
`Buffers` reduction and per-chunk access-path improvement), not a reduction in the number of chunks the
planner must still visit — that remains `INGEST-016`'s (forward-only) job.

Read the migration and test files directly — both match the Implementation/Test acceptance criteria
exactly, including the deliberate `fetched_at`-trailing column order and the reused `_TABLE_SPECS`/
`_HYPERTABLES` three-table ordering convention (no fourth ad hoc table list introduced). `git status`
scoped to `services/ingestion-service/src/` and `connectors/` confirms zero application-code changes
from this ticket (the pre-existing `INGEST-014`/`INGEST-015` diffs remain untouched). `README.md`'s new
paragraph confirmed added ahead of `INGEST-017`'s note, correctly UTF-8 encoded (`git diff --stat`:
84 insertions/19 deletions for the whole file, consistent with this ticket's one paragraph plus the
already-known, already-verified pre-existing `INGEST-014`/`INGEST-015` content — `grep -c 'â€'` returns
0, no encoding corruption introduced while completing this ticket).

## Analysis

Story: DBOPT-007 (`docs/product/backlog-db-optimization.md`).
`PostgresConnectorRecordRepository.latest_fetched_at` — for each of `price_ohlcv`/`onchain_metric`/
`sentiment_score`, `SELECT max(fetched_at) FROM <table> WHERE tenant_id = :tenant_id AND source =
:source` — is called by `connectors/base.py`'s incremental-fetch path (`run_incremental`) on **every
scheduled crawl**, not just interactively. `fetched_at` is not part of any table's PK/index and is not
the hypertable partitioning column (`open_time`/`timestamp`/`created_utc` are), so TimescaleDB's chunk
exclusion cannot help this query at all — it must visit every chunk that could contain the tenant/
source's rows.

Live-verified by the DBA: `price_ohlcv` scoped to the 79,127-row tenant shows a `Finalize Aggregate`
over an `Append` of per-chunk `Partial Aggregate`s touching all 472 chunks (`Buffers: shared hit=2907`),
24ms execution — not slow yet, but running on every incremental crawl for every tenant/source pair, with
cost scaling with chunk count (INGEST-016), not with how recent the tenant's last-fetched row actually
is.

## Design

No design pattern from implementation-plan.md section 7 applies — pure schema/index change. Repository
pattern unaffected: `latest_fetched_at`'s signature/SQL text unchanged — the index changes the query
plan from a full per-chunk aggregate scan to an index-only backward scan taking the first row.

**File(s) touched** (scoped to `services/ingestion-service` only):
- `services/ingestion-service/migrations/versions/0006_add_hypertables_tenant_source_fetched_at_index.py`
  (new Alembic revision, `down_revision = "0005"` — INGEST-017's revision, once merged).
- `services/ingestion-service/README.md` (Documentation AC below).

**DRY check**: grepped `services/ingestion-service/migrations/versions/` and `postgres_repository.py`'s
`_TABLE_SPECS` (the single place the table/event-time-column/default-field mapping already lives, per
INGEST-009/INGEST-012's own precedent) — this migration should iterate the same three tables in the
same order `_TABLE_SPECS`/`0003_convert_to_hypertables.py` already do, not invent a fourth ad hoc list
of table names.

## Implementation acceptance criteria

- New Alembic migration adds, per the DBA's exact migration shape:
  - `CREATE INDEX ix_price_ohlcv_tenant_source_fetched_at ON ingestion.price_ohlcv (tenant_id, source,
    fetched_at);`
  - `CREATE INDEX ix_onchain_metric_tenant_source_fetched_at ON ingestion.onchain_metric (tenant_id,
    source, fetched_at);`
  - `CREATE INDEX ix_sentiment_score_tenant_source_fetched_at ON ingestion.sentiment_score (tenant_id,
    source, fetched_at);`
  - `fetched_at` trailing (not leading) — this is deliberate: `MAX(fetched_at)` for a given
    `(tenant_id, source)` becomes an index-only backward scan taking the first row, not a full
    aggregate.
- Issued against each hypertable's root table (same TimescaleDB root-propagation behavior confirmed for
  VS-026 — this service's TimescaleDB version is the same running container, so the same propagation
  applies; still verify live per Test/Review AC below, don't assume from VS-026's own verification).
- Postgres-only-guarded, same idiom as this service's prior migrations.
- `downgrade()` drops all three indexes, Postgres-guarded.
- Zero changes to `src/app/repositories/postgres_repository.py`, `connectors/base.py`, or any
  router/business-logic file — the query text of `latest_fetched_at` does not change, only its plan.

## Test acceptance criteria

- Existing test suite (including `tests/test_base.py`'s `latest_watermark`/`run_incremental` coverage)
  passes unmodified.
- A new migration test confirms all three indexes exist (on the hypertable root, and propagated to
  existing chunks — same chunk-catalog verification approach as VS-026) after `alembic upgrade head`
  against a real Postgres `DATABASE_URL` (skip-guarded absent a real Postgres).
- Not applicable: no `libs/naive_first_engine` regression gate.

## Review acceptance criteria (Tech Lead verifies personally)

- Live `EXPLAIN (ANALYZE, BUFFERS)` re-run against the real running Postgres container, on the exact
  query shape the DBA measured (`SELECT max(fetched_at) FROM ingestion.price_ohlcv WHERE tenant_id = :t
  AND source = :s`), scoped to the real 79,127-row tenant/source pair, confirming the plan no longer
  shows a 472-chunk `Append`/`Finalize Aggregate` — expect a much narrower, index-driven plan (ideally
  an index-only backward scan per relevant chunk) and materially lower `Buffers: shared hit` than the
  DBA's measured 2907. Repeat for `onchain_metric` against its own real tenant data. Before/after plans
  both captured for at least `price_ohlcv`.
- Personally re-confirm chunk-propagation (same method as VS-026's Review AC) rather than trusting the
  dev agent's report.
- Full `services/ingestion-service` test suite re-run directly by the Tech Lead, zero regressions.
- `git status` scoped to `services/ingestion-service/src/` and `connectors/` confirms zero
  application-code changes.

## Documentation acceptance criteria

- `services/ingestion-service/README.md`'s "`ingestion` Postgres schema" section gains a note: all
  three hypertables now have a composite index on `(tenant_id, source, fetched_at)` (`INGEST-018`/
  `DBOPT-007`), naming the migration file and the query it serves (`latest_fetched_at`, called on every
  incremental crawl).
- `docs/product/backlog-db-optimization.md`'s DBOPT-007 entry marked done at sprint close-out once
  Review criteria pass.
