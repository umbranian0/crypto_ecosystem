# TRUST-003 — Per-run engine/config fingerprint (`validation-service` + `libs/common`)

**Sprint**: 56. **Modules**: `services/validation-service` (migration + repositories + `POST /runs`
handler) and `libs/common` (`naive_first_common.contracts.RunDetailResponse`). **Status**: todo.
**Priority**: Should (backlog priority; sprint sequencing places it first — see "Depends on").
**Depends on**: none. **Blocks**: `TRUST-004` (that ticket cannot be implemented or tested until
`engine_version`/`config_fingerprint` exist on `runs` and on `RunDetailResponse` and are actually
populated at `POST /runs` time).
**Can run in parallel with**: nothing this sprint (`TRUST-004` is strictly sequential after this ticket
is Tech-Lead-verified done — see `docs/sprints/sprint-56.md`'s "Why TRUST-003 strictly precedes
TRUST-004" section).

**Two-module scope, disclosed**: this ticket spans `services/validation-service` and `libs/common`
rather than being split into two tickets. The sprint plan's own "Module/dependency note" explicitly
recommends this grouping ("the column and the contract field are one logical unit of work") — a
migration/handler change with no corresponding contract field would leave `RunDetailResponse` lying
about what the persisted row actually contains, and a contract field with no migration/handler behind
it would be dead schema. Splitting them into two tickets would create an artificial window where one
half is "done" and the other isn't, for a change that is not independently shippable in either
direction. Kept as one ticket, one dev pass, reviewed as one unit.

## Analysis

Covers `docs/product/backlog-trust-and-admin-ops.md`'s `TRUST-003` acceptance criteria in full. Verified
directly against the real code (not taken on trust from `docs/sprints/sprint-56.md`'s own citations,
though those citations held up under re-verification):

- `services/validation-service/migrations/versions/`: current head is `0011_add_split_points_table.py`
  (`revision = '0011'`, `down_revision = '0010'`). The next migration is **`0012`**, `down_revision =
  '0011'`.
- `0008_add_runs_warnings_column.py`/`0009_add_runs_feature_lineage_column.py`: both a single
  `op.add_column('runs', sa.Column(..., nullable=False, server_default='[]'))` in `upgrade()`, mirrored
  `op.drop_column` in `downgrade()`. **This ticket's two columns must NOT copy the
  `nullable=False, server_default=...` half of that shape** — `engine_version`/`config_fingerprint` are
  `nullable=True`, **no** `server_default` at all, so every pre-migration row stays genuinely `NULL`
  after `alembic upgrade head` runs, never backfilled with a fabricated value. Same "plain
  `op.add_column`, portable type" idiom as 0008/0009; different, deliberate nullability/default shape.
- `services/validation-service/src/app/routers/runs.py`'s `create_run` handler (read in full): the run
  row is created via the local `_persist_new_run(...)` helper, called at three sites — the dataset-load
  failure branch (line ~331), the feature-assembly failure branch (line ~363), and the main path (line
  ~443, "Created before the try below (VS-012) so a run.id always exists..."), all three strictly before
  `run_validation_protocol(series, run_config)` is ever invoked (line ~467, inside the following `try`).
  `_persist_new_run`'s own `split_config` dict (`{"train_window", "test_window", "step"}`) is built
  inline inside that helper — this is the exact JSON object `config_fingerprint` must hash. Because
  `_persist_new_run` is the single call site for `run_repository.create_run(...)`, both new fields can be
  computed there and threaded through, with **zero reordering** of the existing handler flow.
- **Binding, explicit decision for this ticket** (sprint's own DoD note): since `_persist_new_run` runs
  at all three call sites — including both failure branches — **every run row created from this
  migration forward gets a non-null `engine_version`/`config_fingerprint`, regardless of whether the run
  subsequently succeeds or fails.** This is correct, not an oversight: the fingerprint describes the
  engine version and config that were *about to be used* for that run attempt, a fact that is true and
  knowable the instant the row is created, independent of whether `run_validation_protocol` later raises.
  The "null only for pre-migration runs" guarantee refers to migration boundary, not run outcome.
- `libs/naive_first_engine/pyproject.toml`: `[project] version = "0.1.0"`, confirmed real and bumpable.
  Source it via `importlib.metadata.version("naive_first_engine")` (reads the installed distribution's
  metadata) rather than parsing the TOML at runtime — correct even if a pinned wheel build ever diverges
  from the source tree's `pyproject.toml`.
- `libs/common/src/naive_first_common/contracts.py`'s `RunDetailResponse` (read in full): current fields
  do not include `engine_version`/`config_fingerprint`. Every existing optional/derived field on this
  model defaults to a safe value (`[]`, `False`, `None`) so a response that temporarily omits a field
  during a rolling deploy doesn't break `gateway-api`'s/`dashboard-web`'s/`reporting-service`'s own
  `RunDetailResponse(**response.json())` reconstruction (all three confirmed, by direct grep, to
  reconstruct this exact way — `services/gateway-api/src/app/routers/runs.py:199`,
  `services/dashboard-web/src/app/routers/runs.py:1119/1164`,
  `services/reporting-service/src/app/generation.py:114`). Both new fields follow that same precedent:
  `str | None = None`.
- `services/validation-service/src/app/repositories/interfaces.py`'s `RunRecord`
  (`@dataclass(frozen=True)`) and `ValidationRunRepository.create_run` Protocol signature, and both
  `sqlite_repository.py`/`postgres_repository.py` implementations (`_run_to_record`, `create_run`) need
  the same two fields threaded through, mirroring exactly how `warnings`/`feature_lineage`/`label` were
  each added previously (optional keyword arg, default `None`, stored on the SQLAlchemy `Run` model,
  read back in `_run_to_record`).
- `services/validation-service/tests/test_repository_interfaces.py`'s `_FakeValidationRunRepository` is
  a structural-conformance fixture only (`isinstance(fake, ValidationRunRepository)` against a
  `runtime_checkable Protocol`, which checks method *presence*, not signature) — it is not required to
  gain the two new keyword args to keep passing, and should not be touched by this ticket unless the dev
  finds a reason to.

**DRY check** (grepped before writing this ticket): no `hashlib`/`sha256`/`importlib.metadata` usage
exists anywhere in `services/validation-service` or `libs/common` today — this is new, not a duplicate
of an existing helper. No canonicalized-JSON-hashing helper exists anywhere in the codebase to reuse.

**Leakage-protocol safety check (CLAUDE.md)**: this ticket adds two purely descriptive/metadata fields.
Nothing here changes `generate_splits`, `run_validation_protocol`, baseline computation, or the DM test.
`engine_version`/`config_fingerprint` are computed from data that already exists (the installed
package's own version, and the run's own already-validated `split_config` dict) — they are never fed
back into any validation computation, never used to gate/alter which splits or baselines run, and never
displayed as if they were an accuracy or performance signal.

## Design

**Pattern**: no new design pattern from implementation-plan.md section 7 applies — this is an additive
column + a pure, stateless hashing function, not a Strategy/Repository/Adapter/Factory/Observer/DI
extension point. The existing Repository layer (`ValidationRunRepository`) is extended in place, the
same way `warnings`/`feature_lineage`/`label` were each added to it before.

**Files touched**:
- `services/validation-service/migrations/versions/0012_add_runs_engine_fingerprint_columns.py` (new)
- `services/validation-service/src/app/models.py` (`Run` gains two nullable columns)
- `services/validation-service/src/app/repositories/interfaces.py` (`RunRecord`,
  `ValidationRunRepository.create_run`)
- `services/validation-service/src/app/repositories/sqlite_repository.py` (`_run_to_record`,
  `SQLiteValidationRunRepository.create_run`)
- `services/validation-service/src/app/repositories/postgres_repository.py`
  (`PostgresValidationRunRepository.create_run` — reuses `sqlite_repository._run_to_record`, no
  duplicate conversion function)
- `services/validation-service/src/app/fingerprint.py` (new — the pure hash/version-lookup module)
- `services/validation-service/src/app/routers/runs.py` (`_persist_new_run`, `get_run`)
- `services/validation-service/tests/` (new tests, see below)
- `libs/common/src/naive_first_common/contracts.py` (`RunDetailResponse`)
- `libs/common/README.md` (public-API doc-sync list — `RunDetailResponse` isn't itself re-listed
  per-field there, but see Documentation ACs below)

**New module, `app/fingerprint.py`** (validation-service-local — not `libs/common`, since nothing outside
this service currently needs to *compute* a fingerprint; only *read* the resulting string fields, which
`RunDetailResponse` already carries):

```python
"""TRUST-003: engine version + config fingerprint computation.

Pure, stateless, no I/O beyond one importlib.metadata lookup (memoized) -- no
network, no DB, no naive_first_engine internals touched. Never used to alter
splitting/baseline/DM-test behavior; purely descriptive metadata persisted
alongside the run row it describes.
"""
from __future__ import annotations

import hashlib
import json
from functools import lru_cache
from importlib.metadata import version


@lru_cache(maxsize=1)
def get_engine_version() -> str:
    """`naive_first_engine`'s installed distribution version (e.g. "0.1.0"),
    read from package metadata -- not by parsing pyproject.toml at runtime,
    so this stays correct even if a pinned wheel build ever diverges from the
    source tree. Memoized: the installed version cannot change within a
    running process.
    """
    return version("naive_first_engine")


def compute_config_fingerprint(split_config: dict) -> str:
    """SHA-256 of `split_config`'s canonicalized (sorted-key, no-whitespace)
    JSON serialization -- the same logical config always hashes identically
    regardless of incidental key ordering. `split_config` here is exactly the
    dict `_persist_new_run` already builds and persists verbatim as the
    `runs.split_config` JSON column -- no second, independently-shaped
    config object is hashed.
    """
    canonical = json.dumps(split_config, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(canonical.encode("utf-8")).hexdigest()
```

**Migration** (`0012_add_runs_engine_fingerprint_columns.py`), matching 0008/0009's mechanics but with
the deliberately different nullability/default shape called out in Analysis:

```python
def upgrade() -> None:
    op.add_column("runs", sa.Column("engine_version", sa.String(), nullable=True))
    op.add_column("runs", sa.Column("config_fingerprint", sa.String(), nullable=True))


def downgrade() -> None:
    op.drop_column("runs", "config_fingerprint")
    op.drop_column("runs", "engine_version")
```

No `server_default` on either column — this is the load-bearing, must-not-regress detail: a
`server_default` would silently backfill every pre-migration row with a non-null placeholder value,
which is exactly the fabrication this story exists to prevent.

**`app/models.py`**: `Run` gains
`engine_version: Mapped[str | None] = mapped_column(String, nullable=True)` and
`config_fingerprint: Mapped[str | None] = mapped_column(String, nullable=True)` — no `default=` argument
(unlike `warnings`/`feature_lineage`, which set `default=list` for their nullable=False shape); leaving
no Python-side default means a `Run(...)` constructed without these keyword arguments persists `NULL`,
matching the migration's own no-`server_default` behavior.

**`_persist_new_run`** (`runs.py`) gains the fingerprint computation, inline, once, reused by all three
call sites since they all funnel through this one helper:

```python
def _persist_new_run(
    run_repository,
    tenant: TenantContext,
    request: RunRequest,
    warnings: list[str],
    feature_lineage: list[dict] | None = None,
):
    split_config = {
        "train_window": request.train_window,
        "test_window": request.test_window,
        "step": request.step,
    }
    return run_repository.create_run(
        tenant_id=tenant.tenant_id,
        dataset_id=request.dataset_id,
        horizon=request.horizon,
        purge_gap_hours=request.purge_gap_hours,
        split_config=split_config,
        warnings=warnings,
        feature_lineage=feature_lineage if feature_lineage is not None else [],
        label=request.label,
        engine_version=get_engine_version(),
        config_fingerprint=compute_config_fingerprint(split_config),
    )
```

(`split_config` is built once, as a local variable, and reused for both `create_run`'s existing
`split_config=` argument and the new fingerprint call — no second, independently-constructed dict that
could ever drift from what's actually persisted in the `runs.split_config` column.)

## Implementation acceptance criteria

- [ ] `0012_add_runs_engine_fingerprint_columns.py` adds `runs.engine_version` and
  `runs.config_fingerprint`, both `String`, `nullable=True`, **no `server_default`**; `downgrade()`
  drops both columns.
- [ ] `app/models.py`'s `Run` gains both columns, nullable, no Python-side `default=`.
- [ ] `app/fingerprint.py` (new) provides `get_engine_version() -> str` (memoized
  `importlib.metadata.version("naive_first_engine")` lookup) and
  `compute_config_fingerprint(split_config: dict) -> str` (SHA-256 of the canonicalized, sorted-key JSON
  serialization).
- [ ] `RunRecord` (`interfaces.py`) gains `engine_version: str | None = None`,
  `config_fingerprint: str | None = None`.
- [ ] `ValidationRunRepository.create_run`'s Protocol signature gains
  `engine_version: str | None = None, config_fingerprint: str | None = None` keyword-only parameters.
- [ ] `SQLiteValidationRunRepository.create_run`/`PostgresValidationRunRepository.create_run` accept and
  persist both fields on the `Run(...)` row they construct; `_run_to_record` (shared by both, defined
  once in `sqlite_repository.py`) reads both back onto the returned `RunRecord`.
- [ ] `_persist_new_run` (`runs.py`) computes `engine_version`/`config_fingerprint` once per call (via
  the new module) and passes them into `run_repository.create_run(...)` — at all three call sites (the
  two failure branches and the main path), since all three already funnel through this one helper.
- [ ] `get_run` (`runs.py`, `GET /runs/{run_id}`) includes `engine_version=run.engine_version,
  config_fingerprint=run.config_fingerprint` in its `RunDetailResponse(...)` construction.
- [ ] `RunDetailResponse` (`libs/common/src/naive_first_common/contracts.py`) gains
  `engine_version: str | None = None`, `config_fingerprint: str | None = None`.
- [ ] No existing field, default, or behavior on any touched file changes for a pre-migration run (a row
  that predates `0012` simply has `NULL`/`None` on both new fields, reads back as `None` through every
  layer, and every other field/response is byte-unchanged).

## Test acceptance criteria

- [ ] Unit test (new, e.g. `tests/test_fingerprint.py`): `compute_config_fingerprint` is deterministic —
  two dicts with identical key/value pairs but different insertion order produce the same hash (proves
  canonicalization, not just "the same object hashes the same as itself").
- [ ] Unit test: `compute_config_fingerprint` is sensitive — two configs differing in exactly one value
  (e.g. `train_window` off by one) produce different hashes.
- [ ] Unit test: `get_engine_version()` returns the real, non-empty version string of the installed
  `naive_first_engine` distribution (e.g. asserts it's a non-empty `str`, or matches
  `importlib.metadata.version("naive_first_engine")` called directly — not a hardcoded `"0.1.0"` literal,
  which would silently go stale on the next real version bump).
- [ ] Integration/handler-level test (extends `tests/test_runs_endpoint.py` or a new file): `POST /runs`
  persists a non-null `engine_version`/`config_fingerprint` on the created run row, readable back via
  `GET /runs/{id}` — both for a run that completes successfully and for a run that fails (e.g. via the
  existing dataset-load-failure fixture pattern `tests/test_failure_handling.py` already uses) — proving
  the "populated regardless of outcome, since it's computed before failure is possible" decision from
  Design/Analysis, not just the happy path.
- [ ] Test proves a run whose row predates migration `0012` (simulate: a `RunRecord`/`Run` row
  constructed without `engine_version`/`config_fingerprint`, or an existing SQLite/Postgres repository
  test fixture inserted before these columns are set) reads back `engine_version=None,
  config_fingerprint=None` through `get_run`/`RunDetailResponse` — never a fabricated value.
- [ ] Existing `services/validation-service` test suite passes unmodified except where this ticket's own
  new keyword arguments require a fixture/fake to be extended (only if a fake's `isinstance` conformance
  actually breaks — confirmed in Analysis it should not, since `runtime_checkable Protocol` only checks
  method presence).
- [ ] `libs/common`'s own test suite (if any covers `contracts.py` field presence/round-tripping) passes
  with the two new optional fields present.
- [ ] This ticket does not touch `libs/naive_first_engine`, a `Baseline`/model-adapter, or a
  feature-engineering step directly — no thesis-numbers regression check applies. (`get_engine_version`
  reads `naive_first_engine`'s package metadata but does not call into, alter, or depend on its
  splitting/baseline/DM-test behavior in any way.)

## Review acceptance criteria (Tech Lead verifies personally)

- Reads the real `git diff` for every touched file; confirms the migration has no `server_default` on
  either column (this is the single highest-stakes line in this ticket — a `server_default` here would
  silently fabricate fingerprints for every pre-migration row).
- Confirms, by reading the migration file directly, that its shape (revision id, `down_revision`,
  `op.add_column`/`op.drop_column` structure) matches the 0008/0009 precedent mechanically, and that
  `down_revision` correctly points at `0011` (the real current head, independently confirmed by listing
  `migrations/versions/`, not assumed from the sprint plan's own citation).
- Confirms `alembic upgrade head` at least loads/recognizes the new migration without a Python
  import/syntax error (via `alembic history`/`alembic check` or an equivalent static check) — and
  discloses plainly whether a live Postgres/SQLite target was actually available in this sandbox to run
  a real `alembic upgrade head`, rather than silently presenting a static check as if it were a live one.
- Personally runs `services/validation-service`'s full test suite (not just the new/changed tests) and
  confirms it passes clean.
- Confirms `compute_config_fingerprint`'s determinism/sensitivity tests are genuine (different dict
  insertion order, not different dict identity; a genuinely differing value, not a no-op change).
- Confirms `_persist_new_run`'s fingerprint computation happens at all three call sites (both failure
  branches, main path) by reading the diff, not by trusting the ticket's own Design section description.
- Confirms no code path anywhere computes a fingerprint for, or otherwise mutates, a pre-migration run
  row — `engine_version`/`config_fingerprint` are write-once at `create_run` time, never touched by
  `update_run_status` or any other mutation path.
- Confirms nothing in this ticket alters `generate_splits`/`run_validation_protocol`/baseline/DM-test
  behavior (positioning/leakage check, CLAUDE.md) — the new fields are read-only metadata everywhere
  outside `_persist_new_run`'s own construction call.

## Documentation acceptance criteria

- [ ] `services/validation-service/README.md` gets a new `TRUST-003` section (or an addition adjacent to
  the existing `warnings`/`feature_lineage`/`label` migration-precedent paragraphs) documenting: the two
  new nullable, no-`server_default` columns; the `app/fingerprint.py` module and what it computes; that
  every run created from migration `0012` forward gets both fields populated at `create_run` time
  regardless of eventual run outcome; and that pre-`0012` rows stay honestly `NULL`, never backfilled.
- [ ] `libs/common/README.md`'s `contracts.py` section (or its own `RunDetailResponse` field
  documentation, if the machine-checked public-API list needs no per-field entry) notes the two new
  optional fields and their "null means either not-yet-computed by an in-flight rolling deploy, or
  predates this migration" dual meaning.
- [ ] `docs/product/backlog-trust-and-admin-ops.md`'s `TRUST-003` entry marked done, all four
  acceptance-criteria boxes checked, pointing to this ticket file. (Tech Lead completes this in the
  review pass, per this repo's convention — see `RPT-003`'s own precedent.)
- [ ] `docs/tickets/README.md` gets a new Sprint 56 section listing this ticket and its status. (Tech
  Lead updates this, per this repo's standing convention.)
