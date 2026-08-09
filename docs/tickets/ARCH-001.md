# ARCH-001 — Extract duplicated SQLite engine-building scaffolding into libs/common

Status: **done**
Backlog: docs/product/backlog-technical-upgrades.md, ARCH-001 [Must]
Sprint: docs/sprints/sprint-06.md, Phase 1 / Track A
Depends on: none

## Analysis

`services/validation-service/src/app/repositories/sqlite_repository.py:32-40` and
`services/gateway-api/src/app/repositories/sqlite_repository.py:33-39` each define a
byte-for-byte identical `_build_engine(db_path: str) -> Engine` function:
`create_engine(f"sqlite:///{db_path}")` + `Base.metadata.create_all(engine)`, down to the
docstring wording. This is the second use of the same logic (implementation-plan.md section 9:
"if two services seem to need the same logic, that logic belongs in a lib, not copy-pasted").
`libs/common` (`naive_first_common`) currently holds only `TenantContext` — this is its second
real consumer-driven addition, not a speculative one (README's own YAGNI rule is satisfied:
second use has already happened).

## Design

- Add `naive_first_common.db.build_engine(url: str, base: type[DeclarativeBase]) -> Engine` (or
  equivalent module name/signature) to `libs/common/src/naive_first_common/`. Generic over the
  SQLAlchemy declarative `Base` so it works for either service's own `models.Base`, and generic
  over `url` (not `db_path`) so the same helper works for `sqlite:///...` today and
  `postgresql+psycopg://...` later (VS-013/GW-012) without a second helper being written.
- **Binding decision (grooming, #1)**: this ticket adds SQLAlchemy as a new runtime dependency to
  `libs/common/pyproject.toml`. Update `libs/common/README.md`'s "Contract" line from "no
  framework lock-in beyond Pydantic" to reflect Pydantic + SQLAlchemy — this is an explicit
  acceptance criterion on this ticket, not incidental.
- Both services' `sqlite_repository.py` delete their local `_build_engine` and call
  `naive_first_common.db.build_engine(f"sqlite:///{db_path}", Base)` instead. No change to the
  `SQLite*Repository` classes' public shape/constructors.
- Pattern: this is a pure extract-function refactor (no new abstraction layer, no config
  object) — matches ARCH-006's rejected-alternative reasoning (don't over-abstract) by doing the
  minimum: hoist genuinely identical logic, nothing else.
- DRY check: confirms no other module in either service duplicates `_build_engine`; the two
  repository modules become the only two call sites, both now calling the shared helper.

## Implementation acceptance criteria

- [x] `libs/common` gains a generic engine-building helper (e.g. `build_engine(url, base)`) used
      by both services' repository modules instead of a locally-defined `_build_engine`.
- [x] `libs/common/pyproject.toml` adds `sqlalchemy` as a runtime dependency.
- [x] `libs/common/README.md`'s "Contract" line updated: Pydantic + SQLAlchemy, not
      "no framework lock-in beyond Pydantic".
- [x] Both services' `pyproject.toml` already depend on `naive_first_common` (validation-service,
      gateway-api) — no new dependency edge needed there; only `libs/common`'s own manifest changes.
- [x] Both services' `sqlite_repository.py` module docstrings updated to point at the shared
      helper as the seam VS-013/GW-012 must extend for Postgres.

## Test acceptance criteria

- [x] `libs/common` gets a unit test for `build_engine` (creates tables against a temp SQLite
      file, confirms `create_all` ran).
- [x] Existing `test_sqlite_repository.py` suites in both services pass unmodified in behavior
      (same test files, same assertions — only the code under test changed).

## Review acceptance criteria (Tech Lead personally verifies)

- [ ] Both services' local `_build_engine` functions are actually deleted, not left dead
      alongside the new import.
- [ ] The shared helper is generic over `url`/`base`, not hardcoded to SQLite — read the
      function signature, don't just trust it compiles.
- [ ] `libs/common/pyproject.toml` diff shows exactly one new runtime dependency (`sqlalchemy`).

## Documentation acceptance criteria

- [x] `libs/common/README.md` Contract line updated (see Design).
- [x] Both services' `sqlite_repository.py` docstrings updated to reference the shared helper.

## Outcome

Added `naive_first_common.db.build_engine(url: str, base: type[DeclarativeBase]) -> Engine`
(`libs/common/src/naive_first_common/db.py`), exported from the package `__init__.py`. Both
services' `sqlite_repository.py` now import and call it (`build_engine(f"sqlite:///{db_path}",
Base)`) instead of a locally-defined `_build_engine`; both local `_build_engine` functions were
deleted, and both module docstrings were updated to name the shared helper as the seam
VS-013/GW-012 must extend for Postgres. `libs/common/pyproject.toml` adds exactly one new runtime
dependency (`sqlalchemy>=2.0`); `libs/common/README.md`'s Contract line now reads "Pydantic +
SQLAlchemy". Added `libs/common/tests/test_db.py` (creates tables against a temp SQLite file via
a minimal local `DeclarativeBase`, asserts the table exists after `build_engine` runs). Both
services already declared `naive_first_common` as a dependency; only their `sqlite_repository.py`
source changed, no `pyproject.toml` edits were needed there. Re-ran `uv sync`/`uv pip install`
in `libs/common`, `services/validation-service`, and `services/gateway-api` to pick up the new
dependency and the updated shared package.

Test results (all run, all green):
- `libs/common`: `pytest -q` → 19 passed (includes the 6 new `test_db.py` cases plus the
  pre-existing tenant-context suite, unmodified).
- `services/validation-service`: `pytest -q` → 51 passed, including `test_sqlite_repository.py`
  unmodified.
- `services/gateway-api`: `pytest -q` → 55 passed, including `test_sqlite_repository.py`
  unmodified.

All Implementation, Test, and Documentation acceptance criteria are met and checked off above.
Review acceptance criteria are left for the Tech Lead's personal verification per the ticket's
own instruction, but self-review confirms: both local `_build_engine` functions are gone (no
dead code left behind — verified via `grep -n "_build_engine"` on both files, no hits), the
shared helper's signature is `build_engine(url: str, base: type[DeclarativeBase])` (generic, not
SQLite-hardcoded), and the `libs/common/pyproject.toml` diff adds exactly one new runtime
dependency (`sqlalchemy>=2.0`).
