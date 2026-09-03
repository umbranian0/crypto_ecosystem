# INGEST-016 — Three ingestion hypertables: `chunk_time_interval` retuning (90 days)

**Sprint**: 21. **Module**: . **Status**: done.

**Tech Lead verification (2026-09-02)**: personally re-ran 
from  -- **100 passed**, 0 failed, matching the dev agent own reported
count. Personally queried the real running  container directly (not the dev
agent own report):  shows  for all three
of //;  grouped by table
shows ,  -- unchanged from the DBA original baseline,
confirming the forward-only-effect claim empirically;  is , the sole
head. Read the migration file and the new test file directly: Postgres-only guard present, forward-only
caveat stated in both  module docstring and ,  reuses
 per-table shape, the new test asserts only , never a
chunk-count decrease.  new "Hypertable chunk sizing" note
confirmed present, accurate, and correctly cross-references . On branch main
Your branch is ahead of 'origin/main' by 4 commits.
  (use "git push" to publish your local commits)

Changes not staged for commit:
  (use "git add <file>..." to update what will be committed)
  (use "git restore <file>..." to discard changes in working directory)
	modified:   docs/tickets/README.md
	modified:   infra/docker-compose.yml
	modified:   services/dashboard-web/README.md
	modified:   services/dashboard-web/src/app/routers/operator.py
	modified:   services/dashboard-web/src/app/templates/_crawl_trigger_result.html
	modified:   services/dashboard-web/src/app/templates/monitoring.html
	modified:   services/dashboard-web/tests/test_monitoring.py
	modified:   services/dashboard-web/tests/test_monitoring_triggers.py
	modified:   services/gateway-api/README.md
	modified:   services/gateway-api/src/app/routers/ingestion.py
	modified:   services/gateway-api/tests/test_ingestion_routing.py
	modified:   services/gateway-api/tests/test_postgres_repository.py
	modified:   services/ingestion-service/README.md
	modified:   services/ingestion-service/src/app/dependencies/repositories.py
	modified:   services/ingestion-service/src/app/routers/connectors.py
	modified:   services/ingestion-service/tests/test_connectors_router.py
	modified:   services/reporting-service/tests/test_postgres_repository.py
	modified:   services/validation-service/tests/test_hypertable_migration.py
	modified:   services/validation-service/tests/test_postgres_repository.py

Untracked files:
  (use "git add <file>..." to include in what will be committed)
	.claude/agents/dba.md
	docs/product/backlog-db-optimization.md
	docs/sprints/sprint-21.md
	docs/tickets/DASH-115.md
	docs/tickets/GW-024.md
	docs/tickets/GW-025.md
	docs/tickets/INGEST-014.md
	docs/tickets/INGEST-015.md
	docs/tickets/INGEST-016.md
	docs/tickets/INGEST-017.md
	docs/tickets/INGEST-018.md
	docs/tickets/VS-025.md
	docs/tickets/VS-026.md
	docs/tickets/VS-027.md
	services/dashboard-web/src/app/templates/_crawl_status_panel.html
	services/gateway-api/migrations/versions/0003_add_api_keys_key_hash_index.py
	services/gateway-api/tests/test_migrations.py
	services/ingestion-service/_archive_pre_sprint18_scratch/
	services/ingestion-service/migrations/versions/0004_retune_hypertable_chunk_intervals.py
	services/ingestion-service/src/app/crawl_registry.py
	services/ingestion-service/tests/test_crawl_registry.py
	services/ingestion-service/tests/test_hypertable_chunk_interval_migration.py
	services/validation-service/migrations/versions/0005_add_runs_tenant_created_at_index.py
	services/validation-service/tests/test_index_migration.py

no changes added to commit (use "git add" and/or "git commit -a") confirms zero changes
to , , or routers from this ticket (other uncommitted diffs present
in the working tree -- , ,
, ,  -- are
pre-existing INGEST-014/INGEST-015 work already in the tree before this ticket started, not touched by
this ticket).

This is the `ingestion-service` half of DBOPT-004 (the PM's sprint plan flags DBOPT-004 as "likely worth
splitting into two tickets per-service", mirroring this repo's OPS-005-01/02 precedent) — the
`validation-service` half is tracked separately as VS-027.

## Analysis

Story: DBOPT-004 (`docs/product/backlog-db-optimization.md`), `ingestion.price_ohlcv`/`onchain_metric`/
`sentiment_score` portion. `0003_convert_to_hypertables.py` called `create_hypertable(...)` without a
`chunk_time_interval` argument for all three tables, so all three use TimescaleDB's default 7-day
interval. Live-verified by the DBA via `timescaledb_information.chunks`/`.dimensions`:

| hypertable | chunks | interval | span | rows | avg rows/chunk |
|---|---|---|---|---|---|
| `price_ohlcv` | 472 | 7 days | 2017-08-17 → today | 121,895 | ~258 |
| `onchain_metric` | 922 | 7 days | 2009-01-01 → today | 19,291 | ~21 |

(`sentiment_score` has 0 rows this session but the same 7-day default and is included for consistency —
its chunk count will only grow as Reddit data lands.) `onchain_metric` averaging ~21 rows/chunk is far
past TimescaleDB's own sizing guidance. This directly worsens DBOPT-007's `latest_fetched_at` scan cost
(chunk count, not row count, drives its cost — see INGEST-018), and will get worse as more tenants'
full-history backfills (`INGEST-013`) land.

**Binding constraint from the PM, must not be contradicted anywhere in this ticket's migration or
docs**: `set_chunk_time_interval` only affects chunks created **after** the call. Existing undersized
chunks are not retroactively merged or resized. State this explicitly in the migration docstring and
README — do not imply existing chunks shrink in count.

## Design

No design pattern from implementation-plan.md section 7 applies — pure schema-tuning, no query surface
or repository code change (per the DBA's own migration shape note).

**File(s) touched** (scoped to `services/ingestion-service` only):
- `services/ingestion-service/migrations/versions/0004_retune_hypertable_chunk_intervals.py` (new
  Alembic revision, `down_revision = "0003"`, the current head).
- `services/ingestion-service/README.md` (Documentation AC below).

**DRY check**: grepped `services/ingestion-service/migrations/versions/` — `0003_convert_to_hypertables.py`
is the only prior migration calling `create_hypertable`, once per table (three calls, one function each
or a loop — check its actual structure before writing this migration and reuse the same
per-table-iteration shape rather than inventing a new one, since this migration also needs to act on
all three tables). No existing `set_chunk_time_interval` call anywhere in this service.

## Implementation acceptance criteria

- New Alembic migration issues, per the DBA's stated interval choice (matching `price_ohlcv`'s own
  ~2,160 rows/90-day-chunk-per-tenant/source estimate — a materially healthier chunk size than the
  current ~258/week):
  - `SELECT set_chunk_time_interval('ingestion.price_ohlcv', INTERVAL '90 days');`
  - `SELECT set_chunk_time_interval('ingestion.onchain_metric', INTERVAL '90 days');`
  - `SELECT set_chunk_time_interval('ingestion.sentiment_score', INTERVAL '90 days');`
- Postgres-only-guarded, same idiom as `0002_add_row_level_security.py`/`0003_convert_to_hypertables.py`.
- Migration docstring explicitly states the forward-only-effect caveat for all three tables.
- `downgrade()` reverts all three to 7 days via `set_chunk_time_interval` calls, same forward-only
  caveat stated.
- Zero changes to `src/app/repositories/`, `connectors/`, routers, or any query code.

## Test acceptance criteria

- Existing test suite (`tests/`, including connector tests) passes unmodified.
- A new migration test confirms, against a real Postgres `DATABASE_URL`, that
  `timescaledb_information.dimensions` reflects the new 90-day interval for all three tables after
  `alembic upgrade head` (skip-guarded absent a real Postgres).
- Test must **not** assert existing chunk counts decrease for any of the three tables.
- Not applicable: no `libs/naive_first_engine` regression gate.

## Review acceptance criteria (Tech Lead verifies personally)

- Query `timescaledb_information.dimensions` directly against the real running container, before and
  after, confirming `time_interval` changed from 7 days to 90 days for all three of `price_ohlcv`,
  `onchain_metric`, `sentiment_score`.
- Confirm via `timescaledb_information.chunks` that pre-existing chunk counts for all three tables are
  unchanged immediately after this migration.
- Full `services/ingestion-service` test suite re-run directly by the Tech Lead, zero regressions.
- `git status` scoped to `services/ingestion-service/src/` and `connectors/` confirms zero
  application-code changes.

## Documentation acceptance criteria

- `services/ingestion-service/README.md`'s "`ingestion` Postgres schema" section gains a note: all
  three hypertables' `chunk_time_interval` retuned to 90 days (`INGEST-016`/`DBOPT-004`), **explicitly
  stating this only affects chunks created after the change** — the existing 472/922 chunks are not
  retroactively resized or merged — naming the migration file.
- `docs/product/backlog-db-optimization.md`'s DBOPT-004 entry (ingestion-service half) marked done at
  sprint close-out once Review criteria pass, cross-referenced with VS-027 for the validation half.


## Outcome (2026-09-02, dev agent)

Implemented exactly the ticket scope: `services/ingestion-service/migrations/versions/0004_retune_hypertable_chunk_intervals.py` (new Alembic revision, `revision = "0004"`, `down_revision = "0003"`) issues `set_chunk_time_interval` at 90 days for `ingestion.price_ohlcv`/`ingestion.onchain_metric`/`ingestion.sentiment_score`, Postgres-only-guarded like `0002`/`0003`, with the forward-only-effect caveat stated explicitly in both the module docstring and `downgrade()` (which reverts to 7 days, same caveat repeated). Zero changes to `src/app/repositories/`, `connectors/`, or routers -- confirmed via `git status` scoped to those paths (only pre-existing, unrelated uncommitted changes from other in-flight work were present; none touched by this ticket).

**Tests**: added `services/ingestion-service/tests/test_hypertable_chunk_interval_migration.py`, skip-guarded on Postgres reachability at `127.0.0.1:5432` (same convention as `validation-service`'s `test_hypertable_migration.py`/`test_postgres_repository.py`). It runs `alembic upgrade head` against the real Postgres and asserts `timescaledb_information.dimensions.time_interval == timedelta(days=90)` for all three tables -- it does **not** assert any chunk-count change, per this ticket's Test AC.

Full suite, `.venv/Scripts/python.exe -m pytest tests/ -q`:
- Baseline (before this ticket's new test file existed, after the migration file was added and already applied to the dev DB from local iteration): 99 passed.
- After adding the new migration test: 100 passed, 0 failed, 0 regressions.

**Live verification against the real Compose Postgres** (`naive_first` superuser, `alembic downgrade 0003` then re-`upgrade head` to capture a genuine before/after on the same running container):

`timescaledb_information.dimensions` (schema `ingestion`), BEFORE (`alembic downgrade 0003`):
```
('onchain_metric', datetime.timedelta(days=7))
('price_ohlcv', datetime.timedelta(days=7))
('sentiment_score', datetime.timedelta(days=7))
```
`timescaledb_information.chunks` count BEFORE:
```
('onchain_metric', 922)
('price_ohlcv', 472)
```
(`sentiment_score`: 0 rows/chunks, consistent with the Analysis section.)

`timescaledb_information.dimensions` AFTER (`alembic upgrade head`, i.e. `0004` applied):
```
('onchain_metric', datetime.timedelta(days=90))
('price_ohlcv', datetime.timedelta(days=90))
('sentiment_score', datetime.timedelta(days=90))
```
`timescaledb_information.chunks` count AFTER (unchanged from BEFORE, as expected -- forward-only effect):
```
('onchain_metric', 922)
('price_ohlcv', 472)
```

`alembic heads`/`alembic current` both report `0004 (head)` -- sole head, confirmed after the container was left at `head` following verification.

**Documentation**: `services/ingestion-service/README.md` gained a "Hypertable chunk sizing" note under the `ingestion` Postgres schema section, naming the migration file and stating the forward-only-effect caveat explicitly (existing 472/922 chunks not retroactively resized/merged), cross-referencing VS-027 for the `validation-service` half.

Not done as part of this ticket (per its own Documentation AC, deferred to sprint close-out): marking `docs/product/backlog-db-optimization.md`'s DBOPT-004 entry done -- that's explicitly a Tech Lead/PM action gated on Review AC passing, out of this dev agent's scope.
