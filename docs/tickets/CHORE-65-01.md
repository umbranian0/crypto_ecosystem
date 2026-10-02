# CHORE-65-01 -- repoint Postgres-backed tests to `naive_first_test` (reporting-service; validation/ingestion if cheap)

**Status: done.** Sprint: docs/sprints/sprint-65.md (Binding constraints, "Test-DB safety"). Follows Sprint 64's gateway-api fix.

## Analysis
Tests hard-code `.../5432/naive_first` (the LIVE DB). Gateway-api's migration tests already wiped `identity.operator_audit_log` once. reporting-service is touched this sprint, so its suite must target `naive_first_test` first. validation-service and ingestion-service have the same hard-coded URLs (see grep `5432/naive_first\b` under services/*/tests); a mechanical repoint is allowed if cheap.

## Design
- Pattern to copy exactly: gateway-api `tests/test_postgres_repository.py` / `tests/test_migrations.py`: `os.environ.get("<SERVICE>_TEST_DATABASE_URL", ".../naive_first_test")`, alembic subprocess gets `DATABASE_URL` = the test URL.
- reporting-service: `tests/test_postgres_repository.py` (POSTGRES_URL line ~70, the `naive_first_app` URL line ~159 which must also point at the test DB, the alembic subprocess at ~240 which must receive `DATABASE_URL` for the test DB). Env var `REPORTING_SERVICE_TEST_DATABASE_URL`. Check for any other hard-coded live-DB reference in reporting tests (grep `naive_first` incl. conftest). Make sure `_postgres_reachable()` skip logic uses the test URL.
- validation-service (`test_chunk_interval_migration.py`, `test_index_migration.py`, `test_hypertable_migration.py`, `test_postgres_repository.py` x3 URLs, `test_split_results_index_migration.py`) and ingestion-service (`test_hypertable_tenant_source_fetched_at_index_migration.py`, `test_hypertable_chunk_interval_migration.py`, `test_dataset_list_continuous_aggregates_migration.py`, `test_crawl_runs_index_migration.py`): same repoint, env vars `VALIDATION_SERVICE_TEST_DATABASE_URL` / `INGESTION_SERVICE_TEST_DATABASE_URL`. Also every alembic subprocess / env passed to them. Do NOT edit non-test code.
- Test DB state (you may prepare it; it is the isolated `naive_first_test` DB, never `naive_first`): currently only extension plpgsql, schema `identity`+`public`. Timescale-dependent tests may need `CREATE EXTENSION IF NOT EXISTS timescaledb` (psql via `docker exec naive-first-postgres psql -U naive_first -d naive_first_test`); role `naive_first_app` is cluster-level. If the test DB cannot be made to support a service's tests cheaply, repoint anyway but record in the ticket that the suite is unverified and must not be run.
- ABSOLUTE RULE: never run any test, alembic command or SQL against the database `naive_first`. Before running any suite, grep that suite's tests for `5432/naive_first\b` (word boundary, not followed by `_test`) and confirm zero hits. Do not touch `operator_audit_log` anywhere. Run each suite only after its repoint.
- Run via the service's own Python env (look how prior tickets ran pytest, e.g. README/Makefile); do not skip the DB-backed tests silently -- report pass/skip counts.

## Implementation AC
No test file under services/reporting-service, validation-service, ingestion-service references live `naive_first` DB (except dashboard-web's unrelated string-redaction fixture, leave it); env override documented in a comment.

## Test AC
reporting-service full suite green with Postgres tests actually executing (not skipped) against `naive_first_test`; validation/ingestion suites run and green, or explicitly recorded as unverified with reason. Report counts.

## Review AC (Tech Lead)
Grep confirms no live-DB URL; read diffs; re-run reporting suite; check `naive_first.operator_audit_log` count unchanged (TL records count before/after).

## Documentation AC
Each touched service README: one line on the test DB and env override. Update this ticket to `done` with outcome and counts.

## Outcome
Repointed every Postgres-backed test in reporting-service (1 file, incl. the `naive_first_app` URL, alembic subprocess, `_postgres_reachable`), validation-service (5 files) and ingestion-service (4 files) from `naive_first` to `naive_first_test` via `<SERVICE>_TEST_DATABASE_URL` env override (default `.../naive_first_test`); comment in each file; README one-liner in each service. Also added a missing `import os` to validation `test_hypertable_migration.py` and replaced `__import__("os")` in two files. No non-test code touched. Final grep `5432/naive_first($|[^_a-z])` over the three services' tests: zero hits (run before every suite). test_models.py alembic runs use sqlite (unchanged). dashboard-web redaction fixture left alone.

Test DB prep (only `naive_first_test`, via `docker exec naive-first-postgres psql -U naive_first -d naive_first_test`): `CREATE SCHEMA IF NOT EXISTS reporting AUTHORIZATION naive_first`, `CREATE SCHEMA IF NOT EXISTS validation`, `CREATE SCHEMA IF NOT EXISTS ingestion`, `CREATE EXTENSION IF NOT EXISTS timescaledb`; then reporting `alembic upgrade head` with `DATABASE_URL` explicitly set to the test URL (reporting tests need tables pre-migrated; validation/ingestion tests migrate themselves).

Commands (each from the service dir, service `.venv`, no `DATABASE_URL` in the shell env):
- reporting-service: `.venv/Scripts/python.exe -m pytest tests -q -rs` -> 86 passed, 4 skipped (all 4 WeasyPrint native libs unavailable; zero Postgres skips).
- validation-service: `.venv/Scripts/python.exe -m pytest tests -q -rs -p no:cacheprovider` -> 261 passed, 0 skipped.
- ingestion-service: same command -> 165 passed, 2 skipped (`onchain_metric`/`sentiment_score` have zero chunks in the empty test DB; propagation check cannot run).

Not verified: `naive_first.operator_audit_log` count before/after (not queried, per the never-touch rule; Tech Lead records it).

## Acceptance
- [x] Implementation, Test, Documentation ACs. Review AC is the Tech Lead's.
