# ARCH-002 — Fix per-request DB engine instantiation

Status: **implemented, pending Tech Lead review**
Backlog: docs/product/backlog-technical-upgrades.md, ARCH-002 [Must]
Sprint: docs/sprints/sprint-06.md, Phase 1 / Track A
Depends on: ARCH-001 (same files, naturally fixed together)

**SPRINT-LEVEL FLAG: this is the single highest-risk ticket in Sprint 06 per the grooming
session. The Tech Lead will personally read the memoization code and re-run BOTH services'
full test suites before marking this done, not just trust a green checkmark.**

## Analysis

`services/validation-service/src/app/dependencies/repositories.py:44-49` and
`services/gateway-api/src/app/dependencies/repositories.py:41-50` construct a brand-new
`SQLite*Repository(_db_path())` on every `Depends()` resolution — i.e. every request. Each
constructor call runs `_build_engine` (now `naive_first_common.db.build_engine` after ARCH-001)
again: `create_engine(...)` per request. Harmless under SQLite (no real pool); would exhaust
Postgres connections under any concurrent load once VS-013/GW-012 land.

## Design

- **Binding decision (grooming, #2): the memoization MUST be keyed on the connection
  string/db_path argument** (e.g. `functools.lru_cache` on a module-level function
  `_get_engine(url: str) -> Engine`), **NOT a zero-arg cache**. A zero-arg cache would break both
  services' existing tests, which swap `VALIDATION_SERVICE_DB_PATH`/`GATEWAY_API_DB_PATH` per
  test via `monkeypatch.setenv` and expect a fresh engine per distinct path/URL — this is not
  optional, it is dictated by existing test behavior this ticket must not regress.
- Concretely: each service's `dependencies/repositories.py` gets a
  `@functools.lru_cache(maxsize=None)` (or equivalent) wrapped function, e.g.
  `_get_engine(url: str) -> Engine: return naive_first_common.db.build_engine(url, Base)`.
  Repository constructors change from taking `db_path: str` and building their own engine, to
  taking (or looking up) the shared, cached `Engine`/session factory for that URL — repository
  objects themselves stay cheap/per-request; only the underlying `Engine` is shared.
- This is the seam ARCH-002 introduces that GW-012's RLS `SET LOCAL` hook (binding decision #8)
  must also hook into later — flag this in the code as the shared engine/session-factory
  provider, since GW-012 will extend it, not replace it.
- Pattern: memoization via `functools.lru_cache` keyed on input, not a singleton/global — matches
  implementation-plan.md section 7's stated avoidance of hidden global state; the cache key
  makes the "which engine for which URL" relationship explicit and testable.
- DRY check: one `_get_engine`-shaped helper per service (can't be fully shared across services
  since each has its own `Base`/models module — this is the one place service-specific
  behavior is unavoidable given each service owns its own SQLAlchemy `Base`).

## Implementation acceptance criteria

- [x] Engine construction is memoized once per process **per URL/db_path**, in both services
      (`functools.lru_cache` on a function taking the connection string, or equivalent
      keyed cache — not a zero-arg cache).
- [x] Repository objects remain cheap/per-request but share the single underlying engine for a
      given URL.
- [x] A test in each service asserts the same engine (or session factory) is reused across two
      separate dependency resolutions within a process for the *same* URL/db_path.
- [x] A test in each service asserts a *different* engine is returned when the URL/db_path
      differs (proves the cache is correctly keyed, not zero-arg) — this directly protects the
      existing `monkeypatch.setenv`-per-test pattern from silently breaking.

## Test acceptance criteria

- [x] New memoization tests (above) pass.
- [x] Full existing test suites (`test_sqlite_repository.py`, all router/integration tests) pass
      unmodified in behavior in both services — this is the regression-risk ticket; both full
      suites must be run, not just the new tests.

## Review acceptance criteria (Tech Lead personally verifies)

- [ ] Read the actual cache implementation in both services: confirm the cache key is the
      URL/db_path argument, not empty/no-arg.
- [ ] Run `services/validation-service`'s full test suite and `services/gateway-api`'s full test
      suite personally (not delegate-reported) and confirm 0 regressions vs. the pre-sprint
      baseline (VS: 51/51 per Sprint 04 outcome; GW: 55/55 per Sprint 05 outcome, plus any new
      ARCH-001 tests).
- [ ] Confirm no test relies on `monkeypatch.setenv` for the DB path env var without the engine
      actually changing — i.e. confirm the fix doesn't accidentally make tests pass by coincidence.

## Documentation acceptance criteria

- [x] `dependencies/repositories.py` docstrings in both services updated to describe the
      memoized-by-URL engine provider as the seam later Postgres/session work extends.

## Outcome

Implemented as designed. `dependencies/repositories.py` in both services gained a
`@functools.lru_cache(maxsize=None) def _get_engine(url: str) -> Engine` that wraps
`naive_first_common.db.build_engine`, keyed on the full `sqlite:///{db_path}` URL string.
The three (VS: two, GW: three) `get_*_repository()` providers now build the db_path once
and pass `_get_engine(...)`'s result into the repository constructor as an `engine` kwarg,
so all repositories for a given URL share one `Engine` object.

`sqlite_repository.py` constructors in both services gained an `engine: Engine | None = None`
parameter (backward compatible — old `SQLiteXxxRepository(db_path)` call sites, including
`tests/test_sqlite_repository.py`, are untouched and still build their own engine via the
`build_engine` fallback when `engine` isn't passed); only the DI providers pass the memoized
engine explicitly. This was chosen over changing the constructor to *require* an `Engine`
(as the Design's illustrative snippet showed) because `test_sqlite_repository.py` and
`test_runs_endpoint.py`/`test_provisioning.py` construct these classes directly from a
`db_path` string and are off-limits to edit (ARCH-004 owns `test_sqlite_repository.py`/
`conftest.py` in this sprint) — an optional param preserves the memoization goal without
touching or regressing those call sites.

The "Review acceptance criteria" section above is left unchecked — it is the Tech Lead's own
personal-verification step (per this ticket's sprint-level flag), not something the implementer
self-certifies. For reference: this implementation ran both full suites and got
validation-service 54/54 passed (51 baseline + 3 new memoization tests) and gateway-api 58/58
passed (55 baseline + 3 new memoization tests), both green; and every real-SQLite test in both
services that sets the DB path env var derives the path from pytest's `tmp_path`, which is
unique per test, so the URL-keyed cache never collides across tests.
