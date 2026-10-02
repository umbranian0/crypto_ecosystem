# CHORE-66-01 -- test-DB audit (read-only, Tech Lead)

**Status: done.** Sprint: docs/sprints/sprint-66.md item 6.

## Analysis / Design
Confirm no test module in any service/lib can touch live `naive_first`; close residual hazards by reading. Read-only; fix only if a live default is found.

## Outcome
- Baseline `identity.operator_audit_log`: 34 rows, md5 c6e1ff463c06e4c7ed65692a4f22becc (before any suite).
- Grep over all `tests/**/*.py` for live `/naive_first` URLs: only hit is dashboard-web `test_settings_environment.py` fake secret string (redaction fixture, no connection).
- All Postgres-touching modules (reporting 1, validation 5, ingestion 4, gateway 2 files) default to `naive_first_test` with env override (CHORE-65-01 / Sprint 64).
- Hazard (a) closed: gateway-api, economic-service and validation-service `test_models.py` build `{**os.environ, "DATABASE_URL": sqlite:///<tmp>}`; the explicit key follows the spread so it wins over any shell-exported live URL. economic-service has no Postgres test; its repository reads `os.environ` only for a sqlite path variable.
- Hazard (b) closed: dashboard-web e2e conftest spawns uvicorn with `**os.environ`; dashboard-web has no DB access.
- Other shared-state notes (not DB, not changed): validation `test_dataset_source.py` writes then deletes a uuid-named object in the live MinIO bucket `naive-first` (self-cleaning, skipped if MinIO unreachable); redis tests use `REDIS_URL` default db 0.
- `naive_first_test` has schemas identity, ingestion, validation, reporting; role `naive_first_app` is cluster-level.
- No live-DB default found; no code changed.
