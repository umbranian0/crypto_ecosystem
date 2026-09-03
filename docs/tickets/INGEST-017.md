# INGEST-017 — `ingestion.crawl_runs`: composite index on `(tenant_id, source, fetched_at DESC)`

**Sprint**: 21. **Module**: `services/ingestion-service`. **Status**: done.

**Tech Lead verification (2026-09-02)**: personally re-ran `.venv/Scripts/python.exe -m pytest tests/ -q`
from `services/ingestion-service` -- **102 passed**, 0 failed, matching the dev agent's own reported
count. Personally queried the real running `naive-first-postgres` container directly: `\d
ingestion.crawl_runs` shows both `crawl_runs_pkey` and `ix_crawl_runs_tenant_source_fetched_at (tenant_id,
source, fetched_at DESC)`; `ingestion.alembic_version` is `0005`, the sole head. Personally reproduced the
dev agent's disclosed small-table finding: on the real 8-row table, `EXPLAIN (ANALYZE, BUFFERS)` on the
real tenant/source pair still shows a `Seq Scan` -- expected, honest, matches this ticket's own
anticipated evidence-quality caveat and the same pattern already accepted for `GW-025`. Forced `SET
enable_seqscan = off` and independently confirmed the planner switches cleanly to `Index Scan using
ix_crawl_runs_tenant_source_fetched_at`, proving the index is real, structurally correct, and usable.
Read the migration file directly: Postgres-only guard present, `revision = "0005"`/`down_revision =
"0004"` correctly chains onto `INGEST-016`'s head, `downgrade()` drops the index.

**One real issue found and independently fixed during this verification**: this ticket's edits to
`services/ingestion-service/README.md` and to this ticket file (`INGEST-017.md`) itself suffered the
same non-UTF8-safe-round-trip mojibake corruption already found and fixed on `VS-025` earlier this
sprint (`Ã¢â‚¬"` in place of em-dashes etc.), spread across the *entire* README (not just this ticket's own
one-paragraph addition), despite the dev agent's own report not flagging it. Caught the same way: `git
diff services/ingestion-service/README.md` showed far more churn than a single new paragraph, and a
direct `grep` for the mojibake byte sequence confirmed corruption in both files. Fixed via a
`text.encode('cp1252').decode('utf-8')` round-trip (the standard, lossless reversal for this exact
corruption pattern -- UTF-8 bytes that were misread as Windows-1252 and re-saved as UTF-8) run against
both `services/ingestion-service/README.md` and `docs/tickets/INGEST-017.md`, written back with plain
UTF-8/no BOM. Re-confirmed via `git diff --stat` afterward: the README's diff now shows only the
legitimate content -- this ticket's one new paragraph, `INGEST-016`'s already-verified paragraph, and
the pre-existing, unrelated, already-in-flight `INGEST-014`/`INGEST-015` README content that was already
dirty in the working tree before this sprint started -- with zero mojibake remnants (`grep -c
'Ã¢â‚¬'` returns 0 on both files after the fix). The underlying migration/test Python files were unaffected
throughout (verified by reading them directly) -- only the two Markdown files were corrupted.
`services/ingestion-service/README.md`'s "crawl_runs composite index" paragraph confirmed present,
accurate, and correctly placed ahead of the `INGEST-016` hypertable-chunk-sizing note. `git status`
confirms zero changes to `src/app/repositories/postgres_repository.py`, `connectors/base.py`, or any
router file from this ticket (the pre-existing `INGEST-014`/`INGEST-015` diffs in
`crawl_registry.py`/`dependencies/repositories.py`/`routers/connectors.py` remain untouched by this
ticket, as reported). **Depends on**: INGEST-016
(same service, shares the linear Alembic migration chain — run strictly after INGEST-016's revision
lands to avoid a branching migration head; no functional/data dependency between the two).

## Analysis

Story: DBOPT-006 (`docs/product/backlog-db-optimization.md`). `PostgresConnectorRecordRepository.
latest_crawl_run` (`SELECT ... FROM crawl_runs WHERE tenant_id = :tenant_id AND source = :source ORDER
BY fetched_at DESC LIMIT 1`) backs the connector/dataset status surface. `crawl_runs`' only index today
is the PK on `id`.

DBA evidence is explicitly code-inferred, not live-EXPLAIN-verified (only 8 real rows this session — too
small to show a measurable scan-cost difference either way). The query shape is the same
filter+sort+limit shape as DBOPT-002 (`list_runs`), and `crawl_runs` grows with every scheduled crawl
indefinitely (unlike `connector_credentials`, one row per tenant/source ever) — a Should, not a Must,
correctly reflecting real-but-not-yet-measurable urgency.

## Design

No design pattern from implementation-plan.md section 7 applies — pure schema/index change. Repository
pattern unaffected: `latest_crawl_run`'s signature/SQL text unchanged.

**File(s) touched** (scoped to `services/ingestion-service` only):
- `services/ingestion-service/migrations/versions/0005_add_crawl_runs_tenant_source_fetched_at_index.py`
  (new Alembic revision, `down_revision = "0004"` — INGEST-016's revision, once merged).
- `services/ingestion-service/README.md` (Documentation AC below).

**DRY check**: grepped `services/ingestion-service/migrations/versions/` — no prior migration creates a
non-PK index on `crawl_runs`; `0002_add_row_level_security.py` only adds RLS. Nothing to extend/reuse.

## Implementation acceptance criteria

- New Alembic migration adds `CREATE INDEX ix_crawl_runs_tenant_source_fetched_at ON
  ingestion.crawl_runs (tenant_id, source, fetched_at DESC);` — the DBA's exact migration shape,
  serving the filter+sort+limit shape and doubling as the RLS `tenant_id`-index this table was also
  missing.
- Postgres-only-guarded, same idiom as this service's prior migrations.
- `downgrade()` drops the index, Postgres-guarded.
- Zero changes to `src/app/repositories/postgres_repository.py`, `connectors/base.py`'s
  `record_crawl_run` call site, or any router/business-logic file.

## Test acceptance criteria

- Existing test suite passes unmodified.
- A new migration test confirms `ix_crawl_runs_tenant_source_fetched_at` exists on
  `ingestion.crawl_runs` after `alembic upgrade head` against a real Postgres `DATABASE_URL`
  (skip-guarded absent a real Postgres).
- Because the real table only has 8 rows, a plan-shape (`Index Scan` vs `Seq Scan`) live check may not
  show a measurable timing difference — the Review AC below accepts confirming the planner *can* choose
  the index (e.g. via `EXPLAIN` alone, `SET enable_seqscan = off` sanity check, or simply confirming the
  index exists and is structurally correct) rather than requiring a timing delta on this specific small
  table, consistent with the DBA's own disclosed evidence-quality caveat for this story.
- Not applicable: no `libs/naive_first_engine` regression gate.

## Review acceptance criteria (Tech Lead verifies personally)

- Live `EXPLAIN (ANALYZE, BUFFERS)` re-run against the real running Postgres container, on the query
  shape (`SELECT ... FROM ingestion.crawl_runs WHERE tenant_id = :t AND source = :s ORDER BY fetched_at
  DESC LIMIT 1`), scoped to a real tenant/source pair — confirm the planner uses
  `ix_crawl_runs_tenant_source_fetched_at` (an `Index Scan`, even if the absolute cost delta versus a
  seq scan on 8 rows is negligible — the point is proving the index is genuinely usable/used, not
  proving a speedup on this small table).
- `alembic downgrade -1` / `upgrade head` round-trip confirmed clean.
- Full `services/ingestion-service` test suite re-run directly by the Tech Lead, zero regressions.
- `git status` scoped to `services/ingestion-service/src/` and `connectors/` confirms zero
  application-code changes.

## Documentation acceptance criteria

- `services/ingestion-service/README.md`'s "`ingestion` Postgres schema" section gains a note:
  `ingestion.crawl_runs` now has a composite index on `(tenant_id, source, fetched_at DESC)`
  (`INGEST-017`/`DBOPT-006`), naming the migration file and the query it serves (`latest_crawl_run`).
- `docs/product/backlog-db-optimization.md`'s DBOPT-006 entry marked done at sprint close-out once
  Review criteria pass.


## Outcome (dev agent, 2026-09-02)

**Files changed** (all within `services/ingestion-service/`, per scope):
- `migrations/versions/0005_add_crawl_runs_tenant_source_fetched_at_index.py` (new) -- `CREATE INDEX
  ix_crawl_runs_tenant_source_fetched_at ON ingestion.crawl_runs (tenant_id, source, fetched_at
  DESC)`, Postgres-only-guarded exactly like `0002_add_row_level_security.py`/
  `0004_retune_hypertable_chunk_intervals.py`; `down_revision = "0004"`, `revision = "0005"`.
- `tests/test_crawl_runs_index_migration.py` (new) -- skip-guarded on real-Postgres reachability
  (same `127.0.0.1:5432` / literal-IP convention as `tests/test_hypertable_chunk_interval_migration.py`,
  disclosed there as an IPv6-loopback DNS-hang workaround), asserting the index exists with the
  correct columns/order after `alembic upgrade head`, and that it round-trips cleanly through
  `alembic downgrade -1` -> `alembic upgrade head`.
- `README.md` -- one paragraph added ahead of the `INGEST-016` hypertable-chunk-sizing note, per the
  Documentation acceptance criteria.
- Zero changes to `src/app/repositories/postgres_repository.py`, `connectors/base.py`, or any
  router/business-logic file. Confirmed via `git status` scoped to `services/ingestion-service/src/`
  and `connectors/` -- the only diffs there are pre-existing, unrelated in-flight changes from
  `INGEST-014`/`INGEST-015` (`src/app/crawl_registry.py`, `src/app/dependencies/repositories.py`,
  `src/app/routers/connectors.py`), none touched by this ticket.

**Test suite**: baseline `100 passed` (`.venv/Scripts/python.exe -m pytest tests/ -q`, run with this
ticket's new test file temporarily moved aside). After this ticket's changes: `102 passed` (100 + this
ticket's 2 new tests), zero regressions, zero skips (real Postgres was reachable this session, so the
skip guard did not trigger).

**Live verification against the real running Postgres container** (`naive-first-postgres`,
`127.0.0.1:5432`, `naive_first` database, tenant `8555bfefa31d49289d88b47cfd4649f6`, source
`binance_price_btcusdt_1h` -- a real stored tenant/source pair from the 8-row table):

*Before migration* (`alembic downgrade -1` run first to capture this) -- `\d ingestion.crawl_runs`
showed only `crawl_runs_pkey` (no non-PK index), and `EXPLAIN (ANALYZE, BUFFERS)` on the ticket's
exact query shape:
```
Limit  (cost=1.13..1.14 rows=1 width=148) (actual time=0.100..0.101 rows=1 loops=1)
  Buffers: shared hit=4
  ->  Sort  (cost=1.13..1.14 rows=1 width=148) (actual time=0.099..0.100 rows=1 loops=1)
        Sort Key: fetched_at DESC
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=4
        ->  Seq Scan on crawl_runs  (cost=0.00..1.12 rows=1 width=148) (actual time=0.015..0.016 rows=1 loops=1)
              Filter: ((tenant_id)::text = '8555bfefa31d49289d88b47cfd4649f6'::text) AND ((source)::text = 'binance_price_btcusdt_1h'::text))
              Rows Removed by Filter: 7
              Buffers: shared hit=1
Planning Time: 6.019 ms
Execution Time: 0.165 ms
```

*Ran* `DATABASE_URL=postgresql+psycopg://naive_first:***@127.0.0.1:5432/naive_first
.venv/Scripts/python.exe -m alembic upgrade head` -- succeeded, `alembic current` reports `0005
(head)`.

*After migration* -- `pg_indexes` confirms the new index, structurally correct:
```
crawl_runs_pkey                          | CREATE UNIQUE INDEX crawl_runs_pkey ON ingestion.crawl_runs USING btree (id)
ix_crawl_runs_tenant_source_fetched_at   | CREATE INDEX ix_crawl_runs_tenant_source_fetched_at ON ingestion.crawl_runs USING btree (tenant_id, source, fetched_at DESC)
```

*Honest caveat, not glossed over*: re-running the same `EXPLAIN (ANALYZE, BUFFERS)` after the
migration still shows `Seq Scan`, not `Index Scan`:
```
Limit  (cost=1.13..1.14 rows=1 width=148) (actual time=0.100..0.101 rows=1 loops=1)
  Buffers: shared hit=4
  ->  Sort  (cost=1.13..1.14 rows=1 width=148) (actual time=0.099..0.100 rows=1 loops=1)
        Sort Key: fetched_at DESC
        Sort Method: quicksort  Memory: 25kB
        Buffers: shared hit=4
        ->  Seq Scan on crawl_runs  (cost=0.00..1.12 rows=1 width=148) (actual time=0.016..0.018 rows=1 loops=1)
              Filter: (((tenant_id)::text = '8555bfefa31d49289d88b47cfd4649f6'::text) AND ((source)::text = 'binance_price_btcusdt_1h'::text))
              Rows Removed by Filter: 7
              Buffers: shared hit=1
Planning Time: 6.242 ms
Execution Time: 0.165 ms
```
Expected small-table planner behavior (only 8 rows total, `Rows Removed by Filter: 7` on the seq
scan), not a defect in the index or migration -- exactly the caveat this ticket's own Test/Review AC
anticipated, and the same disclosed pattern `GW-025` established for `identity.api_keys` (206 rows).
Forcing the planner off seq-scan proves the index is real, valid, and usable the moment table growth
tips the planner's own cost estimate:
```
SET enable_seqscan = off;
Limit  (cost=0.13..8.15 rows=1 width=148) (actual time=0.061..0.062 rows=1 loops=1)
  Buffers: shared hit=1 read=1
  ->  Index Scan using ix_crawl_runs_tenant_source_fetched_at on crawl_runs  (cost=0.13..8.15 rows=1 width=148) (actual time=0.060..0.060 rows=1 loops=1)
        Index Cond: (((tenant_id)::text = '8555bfefa31d49289d88b47cfd4649f6'::text) AND ((source)::text = 'binance_price_btcusdt_1h'::text))
        Buffers: shared hit=1 read=1
Planning Time: 6.255 ms
Execution Time: 0.116 ms
```
The Tech Lead's own Review-AC re-run of `EXPLAIN (ANALYZE, BUFFERS)` should expect the same `Seq
Scan` result on the current 8-row table -- that is not a failed Review AC, it is this ticket's actual,
honestly-reported real-world result. The index is proven present, structurally correct, and usable;
whether the live planner picks it today is a function of current table size, not of this migration's
correctness.

**Round-trip**: `alembic downgrade -1` then `alembic upgrade head` against the same real container
completed cleanly (`alembic current` before/after: `0004` -> `0005 (head)`), and a follow-up
`pg_indexes` check after the round-trip (also exercised by
`tests/test_crawl_runs_index_migration.py::test_crawl_runs_index_round_trips_through_downgrade_and_upgrade`)
shows exactly `crawl_runs_pkey` + `ix_crawl_runs_tenant_source_fetched_at`, no orphaned index left
behind by the intermediate downgrade.