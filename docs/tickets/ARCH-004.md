# ARCH-004 — Extract duplicated SQLite test-fixture scaffolding into a shared test-utility

Status: **done**
Backlog: docs/product/backlog-technical-upgrades.md, ARCH-004 [Should]
Sprint: docs/sprints/sprint-06.md, Phase 1 / Track A
Depends on: none (bundled with ARCH-001 — same test files)

## Analysis

`services/validation-service/tests/test_sqlite_repository.py:26-31` and
`services/gateway-api/tests/test_sqlite_repository.py:30-35` define byte-identical `db_path`
pytest fixtures, including copy-pasted comment wording. Worth fixing now so VS-013/GW-012's new
Postgres test suites don't hand-copy a third/fourth version of the same fixture concept.

## Design

- **Binding decision (grooming, #6)**: ship as a `naive_first_common.testing` module (or
  equivalent test-extra), imported by both services' `conftest.py`. This makes `libs/common` a
  dev/test dependency of both services for the first time — add it explicitly to both services'
  `pyproject.toml` `[dependency-groups] dev` (or equivalent section), since today both services
  depend on `naive_first_common` only as a runtime dependency.
- `naive_first_common/testing.py` exposes a pytest fixture (e.g. `sqlite_db_path(tmp_path)`)
  that returns `str(tmp_path / "<name>.db")` — genuinely identical logic to what both services
  already hand-copy, no behavior change, just relocation.
- Both services' `tests/conftest.py` import and re-expose it (pytest fixtures must be visible in
  the consuming package's conftest or imported into the test module) so
  `test_sqlite_repository.py` in each service uses the shared fixture instead of a local one.
- Pattern: this is test-scaffolding DRY, same "extract identical function" pattern as ARCH-001 —
  no new abstraction, just one fixture instead of two copies.
- DRY check: confirms both `db_path` fixtures are deleted from the two `test_sqlite_repository.py`
  files after the shared one is wired in — not left dead alongside an unused import.

## Implementation acceptance criteria

- [x] A shared test fixture/helper (`naive_first_common.testing`, imported via a documented
      `conftest.py` pattern) provides the `db_path`-style fixture.
- [x] Both services' `test_sqlite_repository.py` files use it instead of their own local copy.
- [x] Both services' `pyproject.toml` add `naive_first_common` to `[dependency-groups] dev` (it
      is already a runtime dependency, but this ticket is what first makes it a *test-time*
      dependency too, per the binding decision — call this out explicitly even if the runtime
      dependency already satisfies `uv`'s resolution, so the intent is documented, not implicit).

## Test acceptance criteria

- [x] Both services' `test_sqlite_repository.py` suites pass unmodified in behavior after
      switching to the shared fixture.
- [x] `libs/common` gets a small test for the fixture/helper itself (or the fixture is exercised
      transitively by both services' suites, which counts, but prefer a direct test in
      `libs/common/tests/`).

## Review acceptance criteria (Tech Lead personally verifies)

- [x] Confirm both services' local `db_path` fixture definitions are actually removed, not
      shadowed by a same-named local fixture that silently wins over the imported one.
- [x] Confirm `naive_first_common` appears in both services' dev dependency group explicitly.

## Documentation acceptance criteria

- [x] `libs/common/README.md` mentions the `testing` module under "Owns" (test-utility fixtures
      shared across services).

## Outcome

Added `naive_first_common/testing.py` exposing a `sqlite_db_path(tmp_path)` pytest fixture
(identical logic/comment to the two hand-copied `db_path` fixtures it replaces). Both services'
`tests/conftest.py` (new files — neither service had one) import it aliased as `db_path`
(`from naive_first_common.testing import sqlite_db_path as db_path`), so pytest registers it
under the fixture name the existing test files already reference — no changes needed to the
`run_repo`/`split_repo`/`tenant_repo`/etc. fixtures that depend on `db_path`. The local `db_path`
fixture definitions were deleted from both `test_sqlite_repository.py` files. Added
`naive_first_common` to `[dependency-groups] dev` in both services' `pyproject.toml`. Added a
direct test, `libs/common/tests/test_testing.py`, exercising the fixture. `libs/common/README.md`
now lists `naive_first_common.testing` under "Owns".

`uv sync` was run in `libs/common`, `services/validation-service`, and `services/gateway-api`
(via PowerShell after Bash hit the known transient OneDrive file-lock issue on `uv.lock`).

Tests: `libs/common` 20 passed, `services/validation-service` 51 passed, `services/gateway-api`
55 passed.
