# ECON-002 — `economic.*` Postgres schema + Repository pattern for cost/slippage *inputs*

**Status: done** — Tech Lead verified directly: read `models.py`, `repositories/interfaces.py`, `test_no_profitability_columns.py`, `main.py`, and `migrations/versions/0002_add_row_level_security.py` in full; independently re-ran `.venv\Scripts\python.exe -m pytest -q` and confirmed **33 passed, 0 failed** (matches the dev agent's own reported count). Confirmed no `ForeignKey` on `SimulationConfig.validation_run_id`, zero `sqlalchemy` import in `repositories/interfaces.py`, `tenant_id`-first on every Protocol method, RLS `FORCE`d and schema-qualified, and `GET /health` genuinely upgraded to a real `SELECT 1` check with no raw exception/credential leakage on failure. Also confirmed, per the coordinator's specific ask: `git status` and a direct file listing of `services/economic-service/` show no leaked content from the concurrent, unrelated `reporting-service` dev agent that was writing to the same shared scratchpad directory at the same time — every file under `services/economic-service/` is scoped to this ticket's own stated file list, nothing extraneous.

## Analysis
Story: ECON-002 (Must), `docs/product/backlog-economic-service.md`. Depends on: ECON-001 (done). Covers backlog ECON-002's acceptance criteria in full. Constraining docs: implementation-plan.md section 5 (schema-per-service, no cross-schema FKs — `simulation_configs.validation_run_id` is an opaque string/UUID, **never** a foreign key into `validation-service`'s `validation` schema, per "no service reads another service's DB schema directly"), section 7 (Repository pattern), section 9 (Protocol-based interfaces, no ABC, `tenant_id`-first, mirroring VS-003's own binding decision). The load-bearing constraint, restated from sprint-13.md/backlog-economic-service.md and NOT to be softened: this schema stores **simulation-input assumption records only** — `fee_schedules`, `slippage_models`, `simulation_configs`. It must **never** contain an `economic_results`/`pnl`/`profit`/`net_return`-style table or column. A results table would imply a profitability number has legitimately been computed, which begs the exact question ECON-005 exists to gate — this is `ECON-010`'s own explicit Won't, not incidentally covered here.

**DRY check (performed before writing this ticket)**: `services/validation-service/src/app/repositories/interfaces.py` and `src/app/models.py` were read as the direct precedent for Protocol-based repository interfaces + SQLAlchemy declarative models, schema-qualified Alembic migrations (`version_table_schema`), and RLS policy (`migrations/versions/0002_add_row_level_security.py`) — reuse this shape structurally (Protocol interfaces returning plain `@dataclass(frozen=True)` records, zero `sqlalchemy` import in the interface module, `tenant_id` first positional parameter after `self`), do not invent a new interface style. `naive_first_common.db.build_engine` (ARCH-001, already a dependency per ECON-001) must be reused for engine construction — do not hand-roll a second `create_engine` helper.

## Design
**Pattern**: Repository (implementation-plan.md section 7) — keeps Postgres specifics out of business logic so `economic.*` can later move to its own physical DB by swapping the implementation, matching every other service's own precedent.

Files touched (all under `services/economic-service/`, no other module touched):
- `src/app/models.py` — SQLAlchemy 2.0 declarative models: `FeeSchedule`, `SlippageModel`, `SimulationConfig`. Every table has `tenant_id`.
- `migrations/` (new Alembic env, `alembic.ini`) — schema-qualified to `economic` (mirroring `validation-service`'s `migrations/env.py` `version_table_schema="economic"` pattern — required per the INF-005 cross-service `alembic_version` collision finding, not optional).
- `migrations/versions/0001_create_economic_schema.py` — creates the three tables.
- `migrations/versions/0002_add_row_level_security.py` — RLS policy authored on all three tables (enforcement against real non-superuser credentials is a later infra ticket, per INF-014's own precedent — author the policy now, don't re-litigate the sequencing).
- `src/app/repositories/interfaces.py` — `EconomicInputRepository`-style `typing.Protocol` interface(s) (one Protocol per table, or one umbrella Protocol — implementer's choice, document which), plain `@dataclass(frozen=True)` record types.
- `src/app/repositories/sqlite_repository.py` OR `postgres_repository.py` — pick ONE backend for this ticket (backlog explicitly does not require dual-backend on day one). Recommendation: SQLite-only for now (keeps this sprint fully self-contained, no `infra/` dependency, matches sprint-13.md's "this sprint touches only `services/economic-service`" scope) — document this choice explicitly in the README, do not silently decide.
- `src/app/dependencies/repositories.py` — DI providers + `Annotated[..., Depends(...)]` aliases, mirroring `validation-service`'s own file.
- `src/app/main.py` — **upgrade `GET /health`** from ECON-001's hardcoded placeholder to a real DB-connectivity check (mirroring OPS-005-01/02: `SELECT 1` via a memoized engine, generic `503 {"status": "unhealthy", "detail": "database unreachable"}` on failure, no raw exception/connection-string leakage). This is ECON-001's own AC3 requirement ("must be replaced in the same PR that adds the DB dependency") — do not leave the placeholder in place after this ticket.
- `tests/test_models.py`, `tests/test_repository_interfaces.py`, `tests/test_sqlite_repository.py` (or `test_postgres_repository.py`, matching whichever backend chosen), `tests/test_no_profitability_columns.py` (the schema-level regression guard, see below), `tests/test_health.py`.

## Implementation acceptance criteria
- [x] `economic` Postgres schema defined (SQLAlchemy models + Alembic migration, schema-qualified per the `validation-service` `version_table_schema` precedent).
- [x] Tables: `fee_schedules` (tenant_id, exchange/venue label, fee tiers), `slippage_models` (tenant_id, model kind, parameters), `simulation_configs` (tenant_id, references an upstream `validation_run_id` by opaque string/UUID — **not** a foreign key into `validation-service`'s schema). No table stores a computed return/P&L/profitability figure.
- [x] Every table has `tenant_id` and is designed for the same RLS pattern `validation-service`/`gateway-api` already use (policy authored even if enforcement against real non-superuser credentials is a later infra ticket).
- [x] `EconomicInputRepository`-style interfaces defined as `typing.Protocol` (no ABC, `tenant_id`-first parameter, plain dataclass record types, zero `sqlalchemy` import in the interface module) with one interim implementation (SQLite or Postgres-only, implementer's choice, documented).
- [x] `GET /health` upgraded from ECON-001's hardcoded placeholder to a real DB-connectivity check, in this same ticket (per ECON-001's own AC3).

## Test acceptance criteria
- [x] Repository round-trip test for each of the three tables (create + read back).
- [x] Tenant-isolation test: two tenants, cross-tenant read returns nothing (mirroring `validation-service`'s own tenant-isolation test shape).
- [x] **Permanent regression guard, load-bearing for this ticket's whole design decision**: a schema-level test asserting no column/table name in `economic.*` (as actually reflected in `src/app/models.py`'s metadata, introspected programmatically — not a hardcoded list a future column could silently violate) matches a profitability-output naming pattern (`pnl`, `net_return`, `profit`, or equivalent — implementer should also check for `return`/`revenue` as a substring, documenting the exact pattern list chosen). This test must fail loudly if anyone later adds such a column/table.
- [x] `tests/test_health.py`: healthy + DB-unreachable-failure-path cases for the upgraded `/health`.
- [x] `.venv\Scripts\python.exe -m pytest -q` passes with zero failures, no regression on ECON-001's 2 existing tests.

## Review acceptance criteria
- Tech Lead will personally verify by reading `src/app/models.py` and the migration file directly (not trusting the regression test alone, per sprint-13.md's own non-negotiable verification requirement item 4): confirm no table/column name matches `pnl`/`net_return`/`profit`/equivalent anywhere in the `economic` schema.
- Tech Lead will confirm `simulation_configs.validation_run_id` (or equivalent) is a plain string/UUID column, not a SQLAlchemy `ForeignKey` into any other schema.
- Tech Lead will confirm the repository interface module has zero `sqlalchemy` import (grep-confirmed).
- Tech Lead will run the full test suite directly and confirm the reported pass count.

## Documentation acceptance criteria
- [x] `README.md` updated: "Owns" section states the `economic` schema and its inputs-only design decision explicitly (cross-reference `ECON-010`'s Won't); backend choice (SQLite/Postgres) documented; `/health`'s upgrade from placeholder to real check documented.

## Sequencing note
Runs in parallel with ECON-003 (independent files, no shared data — confirmed by reading both stories' acceptance criteria and file lists directly, per sprint-13.md's own sequencing decision).

## Outcome

Implemented SQLite-only, per the ticket's own recommendation, to keep this sprint self-contained (no `infra/` touch). No deviation from the ticket's stated Design beyond that explicitly-invited backend choice.

**Files created:**
- `services/economic-service/src/app/models.py` — `FeeSchedule` (`fee_schedules`), `SlippageModel` (`slippage_models`), `SimulationConfig` (`simulation_configs`); all three `tenant_id`-non-nullable; `SimulationConfig.validation_run_id` is a plain `String` column with zero `ForeignKey`s (verified by `tests/test_models.py::test_simulation_config_validation_run_id_is_not_a_foreign_key` and by direct reading); `fee_schedule_id`/`slippage_model_id` are same-schema `ForeignKey`s (allowed — only cross-*service* FKs are forbidden).
- `services/economic-service/src/app/repositories/interfaces.py` — single umbrella `EconomicInputRepository` `typing.Protocol` (documented choice: one Protocol, not three, since every real caller needs all three tables together — a simulation config always references a fee schedule and a slippage model). Zero `sqlalchemy` import (grep-verified: only `typing`, `dataclasses`, `datetime`). `tenant_id` is the first parameter after `self` on every method. Plain `@dataclass(frozen=True)` records: `FeeScheduleRecord`, `SlippageModelRecord`, `SimulationConfigRecord`.
- `services/economic-service/src/app/repositories/sqlite_repository.py` — `SQLiteEconomicInputRepository`, the sole interim implementation, reusing `naive_first_common.db.build_engine`.
- `services/economic-service/src/app/dependencies/repositories.py` — `get_economic_input_repository`/`get_health_check_engine` DI providers, memoized-by-URL `Engine` (ARCH-002 pattern), `ECONOMIC_SERVICE_DB_PATH` env var (default `./economic.db`).
- `services/economic-service/alembic.ini`, `services/economic-service/migrations/{env.py,script.py.mako,README}` — schema-qualified to `economic` via `version_table_schema`/`SET search_path` (Postgres-only branch, no-op on SQLite, mirroring `validation-service`'s INF-005-driven pattern).
- `services/economic-service/migrations/versions/0001_create_economic_schema.py` — creates the three tables.
- `services/economic-service/migrations/versions/0002_add_row_level_security.py` — `FORCE ROW LEVEL SECURITY` + `tenant_id`-keyed policy on all three tables, Postgres-only (no-op on SQLite), enforcement against real non-superuser credentials deferred to a later infra ticket per the ticket's own instruction.
- `services/economic-service/tests/test_models.py` — round-trip + `tenant_id` non-nullable + `validation_run_id` no-FK + `alembic upgrade head` schema-match tests.
- `services/economic-service/tests/test_repository_interfaces.py` — AST-based zero-`sqlalchemy`-import guard, Protocol non-instantiability, fake-implementation round-trip.
- `services/economic-service/tests/test_sqlite_repository.py` — round-trip tests for all three tables + the load-bearing two-directional tenant-isolation test.
- `services/economic-service/tests/test_no_profitability_columns.py` — the permanent, introspection-based regression guard. Walks `app.models.Base.metadata.tables` programmatically (not a hardcoded snapshot of today's columns) and fails if any table or column name contains, case-insensitively, any of: `pnl`, `profit`, `net_return`, `return`, `revenue` (the last two as substrings, per the ticket's own instruction to check `return`/`revenue` as substrings, not just exact terms). Includes a sanity test confirming the metadata genuinely contains all three expected tables (rules out the guard passing merely because the metadata is empty).
- `services/economic-service/tests/test_health.py` — healthy path + DB-unreachable 503 path (asserts no raw exception/credential text leaks into the response body).
- `services/economic-service/tests/conftest.py` — reuses `naive_first_common.testing.sqlite_db_path` as the `db_path` fixture (ARCH-004 precedent), no new fixture invented.

**Files modified:**
- `services/economic-service/src/app/main.py` — `GET /health` upgraded from ECON-001's hardcoded `{"status": "ok"}` to a real DB-connectivity check (`SELECT 1` via `HealthCheckEngineDep`, generic `503 {"status": "unhealthy", "detail": "database unreachable"}` on failure).
- `services/economic-service/README.md` — added a "Schema (ECON-002)" section (inputs-only design decision cross-referencing `ECON-010`'s Won't, the SQLite-only backend choice and its rationale, the `/health` upgrade, migration/RLS summary); left ECON-001's "Scaffolding" and ECON-003's "Contracts" sections in place, only touching the one `/health` sentence in "Scaffolding" to reflect the upgrade.

**Test results**: `.venv\Scripts\python.exe -m pytest -q` from `services/economic-service/` — **33 passed**, 0 failed (includes ECON-001's original 2 `test_package_imports.py` tests and ECON-003's `test_contracts.py` tests, unmodified and still passing — no regression). 1 unrelated `StarletteDeprecationWarning` (pre-existing, not introduced by this ticket).

**Review acceptance criteria, self-checked ahead of Tech Lead review** (not checkboxed above since that section has no checkboxes in the ticket, reported here for the Tech Lead's convenience):
- `src/app/models.py`: no table/column name matches `pnl`/`net_return`/`profit`/`return`/`revenue` anywhere in the `economic` schema (confirmed by direct reading and by `tests/test_no_profitability_columns.py`).
- `SimulationConfig.validation_run_id` is `Mapped[str] = mapped_column(String, nullable=False)` — no `ForeignKey`.
- `src/app/repositories/interfaces.py` has zero `sqlalchemy` import (grep-confirmed: `from __future__ import annotations`, `import typing`, `from dataclasses import dataclass`, `from datetime import datetime` only).

**No deviations requiring flagging.** All Implementation, Test, and Documentation acceptance criteria are checked off above and verified by the test run reported.
