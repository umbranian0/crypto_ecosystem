# INGEST-019 — Continuous aggregate for `list_datasets`' per-source min/max/count (DBOPT-009)

**Status**: done, with one disclosed Design-section deviation (see Outcome below) requiring Tech Lead
sign-off: the literal "TimescaleDB continuous aggregate" mechanism specified below is not usable given
this service's RLS invariant, and was substituted with a functionally-equivalent plain-materialized-view
+ scheduled-job design that preserves every other part of this ticket's Design/Implementation/Test/
Documentation intent.

**Module**: `services/ingestion-service` only (no other module touched).
**Depends on**: none (independent of DBOPT-005/DBOPT-008 — different schema, no shared table). Sequenced first in Sprint 22 per `docs/sprints/sprint-22.md`; DBOPT-008's ingestion half (INGEST-020) is sequenced after this ticket because it benefits from this aggregate already existing when exercising ingestion-side access patterns during compression correctness testing.

## Analysis

Covers `docs/product/backlog-db-optimization.md` DBOPT-009, now unblocked: the user has explicitly decided that a few minutes of staleness on `list_datasets` is acceptable in exchange for a much cheaper query (per the sprint framing — this was the DBA's own open question, now resolved).

**Current gap** (DBA evidence, `backlog-db-optimization.md` DBOPT-009): `PostgresConnectorRecordRepository.list_datasets` (`src/app/repositories/postgres_repository.py`) runs, for each of `price_ohlcv`/`onchain_metric`/`sentiment_score`, `SELECT source, min(event_time), max(event_time), count(*) ... WHERE tenant_id = :tenant_id GROUP BY source` — a full per-tenant, all-chunks scan with no time predicate to exclude chunks on, backing `GET /datasets` (called on every visit to the dataset-picker UI surface).

**Constraint from the docs**: this must not change `GET /datasets`' response shape (`DatasetSummaryResponse`: `source`, `earliest_timestamp`, `latest_timestamp`, `row_count`) from the caller's perspective (sprint DoD). The accepted staleness window must be documented explicitly in `services/ingestion-service/README.md`, not left implicit (sprint DoD, user's own framing of the tradeoff).

## Design

**Pattern**: none of implementation-plan.md section 7's named patterns apply here (this is schema-tuning + one repository method's query rewrite, not a new extension point) — not forcing Strategy/Factory/etc. where the table doesn't call for one.

**DRY check** (grep run before writing this ticket): `_TABLE_SPECS` (`src/app/repositories/postgres_repository.py`) is the single existing place that maps each of the three tables to its own event-time column; `list_datasets`/`read_series`/`latest_fetched_at` all already iterate it rather than each re-deriving "which table, which column." This ticket's three new continuous aggregates and the rewritten `list_datasets` **must** continue to use `_TABLE_SPECS`' three-table order and column names as the single source of truth — do not invent a fourth ad hoc table list (matching this module's own established convention, see INGEST-018's migration docstring for the precedent).

**Design decision — why a single continuous aggregate per hypertable cannot avoid a second aggregation step**: continuous aggregates require a mandatory `time_bucket(...)` group-by expression — they cannot materialize an all-time min/max/count directly. This ticket therefore materializes one row per `(tenant_id, source, daily bucket)` per hypertable (bucket width `INTERVAL '1 day'` — granularity only affects how many materialized rows exist, not correctness, since `list_datasets` re-aggregates across buckets), and `list_datasets` does a second-level `GROUP BY source` over the (small, materialized) aggregate view: `SELECT source, min(bucket_min), max(bucket_max), sum(bucket_count) FROM <cagg> WHERE tenant_id = :tenant_id GROUP BY source`. This is still the performance win: the second-level query scans a tiny materialized table, not the full hypertable across every chunk.

**Migration** (new file `services/ingestion-service/migrations/versions/0007_add_dataset_list_continuous_aggregates.py`, Postgres-only-guarded exactly like `0002`/`0003`/`0004`/`0005`/`0006`):
- Three continuous aggregates, one per hypertable, named `price_ohlcv_daily_source_summary`, `onchain_metric_daily_source_summary`, `sentiment_score_daily_source_summary`, each:
  ```sql
  CREATE MATERIALIZED VIEW ingestion.<name>
  WITH (timescaledb.continuous, timescaledb.materialized_only = true) AS
  SELECT tenant_id, source,
         time_bucket(INTERVAL '1 day', <event_time_column>) AS bucket,
         min(<event_time_column>) AS bucket_min,
         max(<event_time_column>) AS bucket_max,
         count(*) AS bucket_count
  FROM ingestion.<table>
  GROUP BY tenant_id, source, bucket
  WITH NO DATA;
  ```
  followed by a manual `CALL refresh_continuous_aggregate('ingestion.<name>', NULL, NULL);` so the view is populated with existing history at migration time (not left empty until the first scheduled refresh — `WITH NO DATA` alone would otherwise make `list_datasets` return nothing for pre-existing rows until the first policy run).
  `materialized_only = true` is deliberate: real-time aggregation (the TimescaleDB default) would union the materialized rows with a live scan of the invalidation-window raw rows on every query, which defeats this ticket's whole purpose (avoiding the raw-table scan). We are trading away always-current results by design, per the user's decision.
- A refresh policy per aggregate: `SELECT add_continuous_aggregate_policy('ingestion.<name>', start_offset => NULL, end_offset => INTERVAL '10 minutes', schedule_interval => INTERVAL '5 minutes');` — `end_offset` of 10 minutes plus a 5-minute schedule gives an accepted staleness window of roughly 10-15 minutes for the most recent data (state this precisely, based on what you actually observe live, not the theoretical number, in the ticket's Outcome notes and in the README per the Documentation AC below — if live testing shows a different actual staleness, document the real number, don't leave the theoretical one uncorrected).
- `downgrade()` drops the three continuous aggregates and their policies, following the Postgres-only guard idiom.

**Repository code** (`src/app/repositories/postgres_repository.py`): rewrite `list_datasets` to query each of the three new aggregate views (via `sqlalchemy.text`, since these are unmapped views, not ORM models — same raw-SQL precedent this module already uses for the migrations, not a new pattern) instead of the raw hypertables, applying the second-level `GROUP BY source` described above. Keep the exact same `_tenant_scoped_session`/RLS-scoping call at the top of the method (the continuous aggregate views inherit no RLS of their own — they are plain materialized views, not hypertables with FORCE ROW LEVEL SECURITY — so the `WHERE tenant_id = :tenant_id` predicate in the query itself is now the *only* tenant-isolation mechanism for this one method, not defense-in-depth on top of RLS; document this explicitly in a code comment so a future reader does not assume RLS is still doing the isolation work here). Return type (`DatasetSummary`) and the router's `DatasetListResponse`/`DatasetSummaryResponse` (`naive_first_common.contracts`) are unchanged — zero changes to `src/app/routers/datasets.py`.

## Implementation acceptance criteria

- AC1: three continuous aggregates + refresh policies created via the migration above, Postgres-only-guarded (a no-op against the SQLite `alembic upgrade head` schema-parity test, matching every prior migration in this service).
- AC2: `list_datasets` queries the three continuous aggregates, not the raw hypertables; `GET /datasets`' response shape (`DatasetSummaryResponse`: `source`, `earliest_timestamp`, `latest_timestamp`, `row_count`) is byte-identical from the caller's perspective — no field added, removed, or renamed.
- AC3: `read_series`/`latest_crawl_run`/`latest_fetched_at`/`add_*_records` are unchanged — this ticket touches only `list_datasets` and the new migration.

## Test acceptance criteria

- A live test (real Postgres, skipped not failed if unreachable, same convention as `test_hypertable_tenant_source_fetched_at_index_migration.py`) confirming: the three continuous aggregates exist after `alembic upgrade head`; each has a live refresh policy (`timescaledb_information.jobs`/`continuous_aggregates`); a real tenant's `PostgresConnectorRecordRepository.list_datasets` call against the real seeded data returns min/max/count values matching a direct raw-hypertable aggregation for the same tenant (i.e., correctness, not just "no error") — after an explicit manual `refresh_continuous_aggregate` call, not relying on the 5-minute scheduled job's timing inside a test run.
- A live staleness-window test: insert one new row into `price_ohlcv` for a test tenant/source, confirm `list_datasets` does **not** yet reflect it (proving `materialized_only = true` genuinely defers to the next refresh, not real-time aggregation), then manually trigger `refresh_continuous_aggregate` and confirm it now does. This is the concrete, non-tautological proof of "eventual consistency," not merely "the aggregate was created."
- Existing `tests/test_datasets_router.py` (uses `FakeConnectorRecordRepository`, unaffected by this ticket's Postgres-only repository change) re-run with zero regressions.
- Full `services/ingestion-service` suite re-run with zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Re-run the live migration/correctness/staleness tests directly against the real running Compose Postgres container myself, not merely trust the dev agent's report.
- Confirm via `git diff` that `src/app/routers/datasets.py` is untouched (zero response-shape risk introduced at the router layer) and that `_TABLE_SPECS` is not duplicated a second time for the new aggregates.
- Confirm the `materialized_only = true` comment/documentation explicitly states RLS does not cover the new views and that `WHERE tenant_id = :tenant_id` is now the sole isolation mechanism for this one method — read the code to confirm the predicate is actually present on every one of the three per-table queries, not just one.
- Confirm the actual observed staleness window (not the theoretical 10-15 minutes) is what gets written into the README.

## Documentation acceptance criteria

- `services/ingestion-service/README.md`'s `list_datasets`/`GET /datasets` section gains an explicit "eventual consistency" caveat: `GET /datasets` now reflects a continuous aggregate refreshed on a fixed schedule, not the always-current raw table; state the real, observed staleness window (not a guess) and that this is a deliberate, user-approved tradeoff (DBOPT-009), not a regression.
- Reference `INGEST-019`/`DBOPT-009` in the same style as the existing `INGEST-016/17/18`/`DBOPT-004/6/7` README entries (ticket id + one-paragraph rationale + evidence).

## Outcome (dev agent, 2026-09-03)

**Design-section deviation requiring explicit Tech Lead sign-off**: the Design section's literal
mechanism (`CREATE MATERIALIZED VIEW ... WITH (timescaledb.continuous, ...)` per hypertable) is not
usable in this environment. Live-reproduced against a disposable scratch hypertable before touching the
real `ingestion` tables: TimescaleDB 2.29.1 refuses `CREATE MATERIALIZED VIEW ... WITH
(timescaledb.continuous, ...)` outright on any hypertable with row-level security enabled (`ERROR:
cannot create continuous aggregate on hypertable with row security`). `price_ohlcv`/`onchain_metric`/
`sentiment_score` all have `FORCE ROW LEVEL SECURITY` (`0002_add_row_level_security.py`, INGEST-002), a
locked-in multi-tenant isolation invariant. A workaround exists and was live-verified safe on the same
scratch hypertable (toggle `relrowsecurity`/`relforcerowsecurity` off only for the duration of the
`CREATE MATERIALIZED VIEW` statement itself, then immediately re-enable within the same migration
transaction) -- but this development environment's own execution safeguards refuse to run any migration
that disables row-level security, even transiently and even with a verified-safe revert in the same
transaction. Per this environment's own guidance for a permission denial ("stop and explain... let the
user decide"), that refusal was treated as authoritative rather than something to route around by
disguising or splitting the SQL.

**Substituted design** (see migration 0007's own docstring and `postgres_repository.py`'s updated
comments for the full detail): three plain Postgres materialized views, same names
(`<table>_daily_source_summary`) and same `(tenant_id, source, daily bucket, bucket_min, bucket_max,
bucket_count)` shape the Design section specified, each with a unique index on `(tenant_id, source,
bucket)` (required for `REFRESH MATERIALIZED VIEW CONCURRENTLY`), refreshed via one shared
`ingestion.refresh_dataset_list_summaries(job_id int, config jsonb)` procedure scheduled every 5 minutes
via TimescaleDB's generic `add_job` (not `add_continuous_aggregate_policy`). This never touches
`ALTER TABLE ... ROW LEVEL SECURITY` at all. `list_datasets`' rewritten query, `GET /datasets`'s response
shape, and `_TABLE_SPECS`'s role as the single source of truth for table order/names are all unchanged
from the Design section's own description -- only the refresh mechanism differs (full periodic recompute
of a small per-day rollup vs. true incremental continuous-aggregate materialization), which does not
change the ticket's core performance goal (a cheap `GET /datasets` read against a small materialized
table instead of a full per-tenant hypertable scan).

**AC1 (three continuous aggregates + refresh policies)**: partially met as literally worded -- the three
materialized views and the shared scheduled refresh job both exist and are live-verified (see Test
results below), but they are not TimescaleDB continuous aggregates / `add_continuous_aggregate_policy`
policies, for the reason above. Functionally equivalent; not checking this box as fully met without
flagging the substitution for Tech Lead review.
**AC2/AC3**: met as written -- `list_datasets` queries the three views (not raw hypertables), `GET
/datasets`' response shape is unchanged, and `read_series`/`latest_crawl_run`/`latest_fetched_at`/
`add_*_records` are untouched.

**Files created/changed** (all within `services/ingestion-service/`, per scope):
- `migrations/versions/0007_add_dataset_list_continuous_aggregates.py` (new) -- three materialized views
  + unique indexes + one shared refresh procedure + one `add_job` schedule (every 5 minutes),
  Postgres-only-guarded; `downgrade()` deletes the scheduled job, drops the procedure, drops the views.
- `src/app/repositories/postgres_repository.py` -- `list_datasets` rewritten to query the three
  `<table>_daily_source_summary` views via raw SQL (`sqlalchemy.text`), doing the second-level
  `GROUP BY source` the Design section specified; module/method-level comments document that these views
  have no RLS of their own and that the `WHERE tenant_id = :tenant_id` predicate is the sole
  tenant-isolation mechanism for this one method.
- `tests/test_dataset_list_continuous_aggregates_migration.py` (new) -- live-Postgres-gated
  (skip-not-fail on unreachable, same convention as this service's other real-Postgres migration tests):
  view-existence, live-scheduled-job, correctness-against-raw-hypertable-aggregation (after a manual
  refresh), and a non-tautological staleness test (insert a row, confirm `list_datasets` does NOT yet
  reflect it, manually refresh, confirm it now does). Uses a distinct, clearly-identifiable test
  tenant/source (`ingest019-test-tenant`/`ingest019_test_source`) and cleans up its own rows (and
  re-refreshes the affected view to drop the resulting stale materialized rows) at the end of every test.
- `README.md` -- `GET /datasets` eventual-consistency caveat added, stating the real observed staleness
  window and the substituted-design note, per the Documentation acceptance criteria.

**Real observed staleness window**: up to ~5 minutes (the scheduled job's `schedule_interval`; a fresh
`add_job` schedule was confirmed live via `timescaledb_information.jobs` with a real `next_start`
5 minutes out). Live-measured full-refresh execution time for all three views against this session's
real backfilled data (121,895 rows in `price_ohlcv` alone) was ~0.6s / ~1.3s / ~0.01s respectively (under
2 seconds combined) -- negligible next to the 5-minute interval, so the effective worst-case staleness is
the schedule interval itself, not materially longer. This is the real number written into the README,
not the ticket's theoretical 10-15 minutes (which assumed an `end_offset` invalidation-window concept
that does not apply to a full-recompute plain materialized view).

**Disclosed side effect requiring Tech Lead awareness**: while diagnosing an unrelated pre-existing gap
(discovered, not introduced, by this ticket -- see below), ad hoc debugging via
`naive_first_common.db.build_engine`'s `Base.metadata.create_all` against a bare (no
`search_path=ingestion` option) Postgres URL created five empty, harmless stray tables in the `public`
schema on the shared UAT container (`public.price_ohlcv`/`onchain_metric`/`sentiment_score`/
`connector_credentials`/`crawl_runs`). Their rows (all from this session's own test data) were deleted;
the tables themselves could not be dropped because this environment's execution safeguards also block
`DROP TABLE` against the real database, even for tables this session itself created. They are empty, are
never targeted by the real application (which always resolves its engine URL through `app.dependencies.
repositories._postgres_engine_url`'s `options=-csearch_path=ingestion`) or by any test in this suite, and
pose no functional risk, but a human with drop privileges should remove them
(`DROP TABLE public.price_ohlcv, public.onchain_metric, public.sentiment_score,
public.connector_credentials, public.crawl_runs;`) at convenience.

**Pre-existing gap discovered, not introduced, by this ticket (out of scope to fix here)**:
`PostgresConnectorRecordRepository`/`PostgresCredentialRepository`, when constructed directly with a
bare `DATABASE_URL` (no `options=-csearch_path=ingestion`), resolve the ORM's unqualified table names
against whatever the connecting role's own default search_path is (`"$user", public` for both
`naive_first` and `naive_first_app`), not the `ingestion` schema -- `app.models` has no explicit
`schema="ingestion"` on any model, so this only works correctly today because the one production caller,
`app/dependencies/repositories.py`'s `_postgres_engine_url`, always appends that connection option by
hand. This ticket's own new test (and my own earlier ad hoc debugging, before I found that helper) hit
this the hard way. Flagging for the Tech Lead/PM backlog, not fixing here: this ticket's file scope is
`list_datasets`/migration 0007 only, and the real app path is already correct via the existing DI helper
-- the gap only bites direct repository construction (as this ticket's own live test necessarily does),
not the running service.

**Test results**: `.venv/Scripts/python.exe -m pytest tests/ -q` from `services/ingestion-service` ->
**114 passed, 1 skipped** (the skip is pre-existing/unrelated:
`test_hypertable_tenant_source_fetched_at_index_migration.py`'s `sentiment_score` chunk-propagation
check, skipped because that table has zero chunks in this environment -- not caused by this ticket).
This ticket's own new file, `tests/test_dataset_list_continuous_aggregates_migration.py`, ran live
against the real `naive-first-postgres` container (not skipped): **6 passed**. `tests/
test_datasets_router.py` (fake-repository-backed, unaffected by this ticket's Postgres-only repository
change) re-run with zero regressions as part of the same full-suite run.

**Confirmed via `git diff --stat services/ingestion-service/src/app/routers/datasets.py`**: no output --
zero changes, as required.
