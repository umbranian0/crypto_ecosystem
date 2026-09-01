# INGEST-002 — `ingestion` Postgres schema: per-tenant hypertables + RLS

**Sprint**: 18. **Module**: `services/ingestion-service`. **Status**: done (2026-08-25) — implemented by the dev agent, pending the Tech Lead's own personal re-run of `alembic upgrade head` against the live Compose Postgres per this ticket's Review acceptance criteria. **Priority**: Must.
**Depends on**: none. **Blocks**: `INGEST-003`, `INGEST-004`, `INGEST-005`, `INGEST-007`, `INGEST-010`.

## Analysis

Story: backlog `INGEST-002`, refined by `docs/solution-design.md` section 8.2. Acceptance criteria
below fold in the schema sketch from 8.2 (five tables, not three — `connector_credentials` and
`crawl_runs` are created here too, since they're schema, not connector-behavior work). Constraint:
`implementation-plan.md` section 5 — schema-per-service, no cross-schema FKs/joins; section 2 — no
other service may ever read this schema directly (this ticket's own AC includes the grep proof).

## Design

No `implementation-plan.md` section 7 pattern applies to a migration file itself (Repository pattern
applies to the code that reads/writes these tables — that's `INGEST-003`/`INGEST-004`/`INGEST-005`,
not this ticket). Files touched (all new, `services/ingestion-service/` only):
- `services/ingestion-service/migrations/env.py`, `migrations/script.py.mako`, `alembic.ini` (new
  Alembic environment — this service has none today)
- `services/ingestion-service/migrations/versions/0001_create_ingestion_schema.py`
- `services/ingestion-service/migrations/versions/0002_add_row_level_security.py`
- `services/ingestion-service/migrations/versions/0003_convert_to_hypertables.py`
- `services/ingestion-service/src/app/models.py` (SQLAlchemy models — new `src/app/` package; this is
  the first file under `src/app/` for this service, shared with `INGEST-007`'s scaffolding, but this
  ticket only adds `models.py`, not `main.py`)
- `services/ingestion-service/pyproject.toml` (new — `uv`-managed; this service currently only has
  `requirements.txt` for the connector scripts, which stays untouched)

**DRY check (grep first)**: `grep -rn "create_hypertable\|FORCE ROW LEVEL SECURITY" services/` before
writing. Confirmed precedents to copy with attribution, not re-derive:
`services/validation-service/migrations/versions/0002_add_row_level_security.py` (RLS policy shape),
`services/validation-service/migrations/versions/0004_convert_split_results_to_hypertable.py`
(hypertable-conversion idiom + widened-PK fix), `services/validation-service/migrations/env.py` and
`services/gateway-api/migrations/env.py` (both already fixed for the cross-service `alembic_version`
collision, `INF-005`/`version_table_schema` — copy that exact fix, do not re-derive it a third time).

## Implementation acceptance criteria

- [x] New Alembic env scoped to the `ingestion` schema specifically for Postgres connections
  (`version_table_schema="ingestion"`, mirroring the `INF-005` fix) — `alembic upgrade head` against
  the real Compose Postgres does not collide with `validation`/`identity`/`reporting`'s own
  `alembic_version` tables.
- [x] Five tables created in the `ingestion` schema, matching solution-design.md 8.2's column sketch
  exactly: `price_ohlcv`, `onchain_metric`, `sentiment_score`, `connector_credentials`, `crawl_runs`.
  `connector_credentials`' credential-value columns are typed `bytea` (ciphertext storage — `INGEST-011`
  writes the actual encrypt/decrypt code, this ticket only needs the column type right).
- [x] `price_ohlcv`/`onchain_metric`/`sentiment_score` are each declared a TimescaleDB hypertable via
  `create_hypertable(..., if_not_exists => TRUE)`, partitioned on `open_time`/`timestamp`/`created_utc`
  respectively, with the primary key widened to include the partitioning column (copy
  `0004_convert_split_results_to_hypertable.py`'s exact fix for this TimescaleDB constraint).
- [x] RLS `ENABLE` + `FORCE` + a `tenant_isolation` policy (`USING (tenant_id =
  current_setting('app.tenant_id')::text)`) on all five tables — byte-identical shape to
  `validation-service`'s `0002_add_row_level_security.py`.
- [x] `services/ingestion-service/pyproject.toml` created (`uv`-managed), dependencies: `sqlalchemy`,
  `alembic`, `psycopg[binary]` — no FastAPI/httpx yet (that's `INGEST-007`'s scope, kept separate so
  this ticket's diff stays schema-only).

## Test acceptance criteria

- [x] `alembic upgrade head` run against a real (or Compose) Postgres succeeds from empty, and running
  it twice is a no-op (idempotent, matching `INF-016`'s convention). Verified live against this repo's
  running `naive-first-postgres` container (`127.0.0.1:5432`, `postgresql+psycopg://` driver): first run
  created all 5 tables + 3 hypertables + RLS + `ingestion.alembic_version` (stamped at `0003`), second
  run was a documented no-op, `alembic current` reported `0003 (head)` both times.
- [x] A test (or a documented manual `psql` check, whichever this service's nascent test setup
  supports) proves RLS actually blocks a cross-tenant unfiltered `SELECT` on at least one of the five
  tables, mirroring `INF-014`'s live-verification method (connect as a non-superuser role, `set_config`
  different tenant ids, confirm row visibility differs). Verified manually: connected as the existing
  non-superuser `naive_first_app` role (after a by-hand `GRANT USAGE`/`SELECT,INSERT,UPDATE,DELETE ON
  ALL TABLES IN SCHEMA ingestion` against the live container, mirroring `RS-002`'s own disclosed
  by-hand-grant precedent — the reproducible fresh-volume version of this grant lives in
  `infra/postgres-init/02-create-app-role.sh`, an infra file out of this ticket's scope to edit), inserted
  two `crawl_runs` rows for `tenant-a`/`tenant-b`, then `SET app.tenant_id = 'tenant-a'` returned only
  that tenant's row, `SET app.tenant_id = 'tenant-b'` returned only the other, and no `app.tenant_id` set
  at all raised a Postgres error (`unrecognized configuration parameter "app.tenant_id"`) rather than
  returning any row — cross-tenant leakage is blocked, not just filtered. Test rows deleted afterward.
- [x] `grep -R "ingestion\." services/validation-service/src services/gateway-api/src
  services/reporting-service/src` returns nothing beyond comments — proves no other service reads this
  schema (this is also a standing acceptance test for every later ticket in this schema's lineage).
  Verified: empty output.

## Review acceptance criteria (Tech Lead verifies personally)

- Migration file diffs match `validation-service`'s RLS/hypertable precedents in *shape*, with
  attribution comments citing the source files (not silently re-derived).
- No file outside `services/ingestion-service/migrations/`, `services/ingestion-service/src/app/models.py`,
  and `services/ingestion-service/pyproject.toml`/`alembic.ini` is touched — confirmed via `git status`
  scoped to `services/ingestion-service/` before and after.
- `alembic upgrade head` personally re-run against the live Compose Postgres, not just trusted from the
  dev agent's report.

**Disclosed gap for the Tech Lead, not fixed by this ticket (outside its file scope)**:
`infra/postgres-init/01-create-schemas.sql` does not yet list `ingestion` alongside
`validation`/`identity`/`reporting`, so a fresh Postgres volume would not have the schema pre-created
the way its four siblings are. Worked around, staying inside `services/ingestion-service/migrations/`,
by having `migrations/env.py` issue `CREATE SCHEMA IF NOT EXISTS ingestion` itself before setting
`search_path` — functionally self-sufficient either way, but folding `ingestion` into
`01-create-schemas.sql` for consistency with its siblings is a real, recommended follow-up (an infra
ticket, not a re-open of this one). Similarly, `naive_first_app`'s grants on the `ingestion` schema were
only applied by hand against the live container for this ticket's own RLS verification (mirroring
`RS-002`'s disclosed precedent) — making that reproducible on a fresh volume means adding `ingestion` to
`infra/postgres-init/02-create-app-role.sh`'s existing `GRANT ... IN SCHEMA validation, identity,
reporting` statements, also left to that same follow-up infra ticket.

## Documentation acceptance criteria

- [x] `services/ingestion-service/README.md`'s "Owns" section updated: the `ingestion` Postgres schema
  is now real (was "not yet built"), naming all five tables.
