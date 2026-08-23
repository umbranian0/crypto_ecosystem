# Ticket index

Eleven sections are tracked here, kept as clearly separated: `libs/naive_first_engine` (NFE-*, Sprint 01+02, done), `services/validation-service` (VS-*, Sprint 03+04+06+09+10+14), `libs/common` (LC-*, Sprint 04+10; ARCH-*, Sprint 06+10), `services/gateway-api` (GW-*, Sprint 05+06+14), `infra` (INF-*, Sprint 06+07+14), the cross-cutting Operability backlog (OPS-*, Sprint 08+09), `services/ingestion-service` (INGEST-*, Sprint 10), `services/dashboard-web` (DASH-*, Sprint 11), `services/reporting-service` (RS-*, Sprint 12), and `services/economic-service` (ECON-*, Sprint 13 — a disclosed, user-authorized override of trigger #11's ethical/business-honesty boundary, scaffolding-only, see that section below for the full framing). Sprint 14 (docs/sprints/sprint-14.md) closes two disclosed capability gaps (`DASH-005-GAP`, `RS-GAP`) across three modules (`validation-service`, `gateway-api`, `infra`) in one sprint — see the "Sprint 14" subsections under each relevant module below. Sprint 06 (docs/sprints/sprint-06.md) spans ARCH-*/INF-*/two VS-*/one GW-* tickets in one debt sprint — see the "Sprint 06" subsections under each relevant module below. Sprint 10 (docs/sprints/sprint-10.md) closes four longstanding pure-documentation debt items (LC-005, ARCH-007, ARCH-008, VS-016) plus one retroactive tracking ticket (INGEST-001) — see the "Sprint 10" subsections under each relevant module below. **Note on the Sprint 12/13 file-content incident (resolved)**: due to a race between two concurrent background agent sessions writing to this repo directory at nearly the same time (Sprint 12's `reporting-service` PM output and Sprint 13's `economic-service` PM output both originally arrived from their respective agents under the same working filename before being placed/renamed), `docs/sprints/sprint-12.md`'s committed content ended up containing `services/economic-service` (ECON-*) planning text instead of `services/reporting-service` content, despite its commit message correctly reading "Sequence Sprint 12: services/reporting-service PoC." The Sprint 12 Tech Lead caught the mismatch independently, correctly did not treat it as authorization to build `economic-service` under Sprint 12, and worked from `docs/product/backlog-reporting-service.md` and its own task instructions directly instead. The file has since been corrected in place, restoring the real `reporting-service` sprint content (recovered from this session's own prior read of the source, not from git history, since the wrong content had already been committed). `docs/sprints/sprint-13.md` (the correct, intact `economic-service` sprint file, including its Outcome section) was unaffected throughout.

# libs/naive_first_engine (NFE-*)

Source: docs/sprints/sprint-01.md, docs/sprints/sprint-02.md, docs/product/backlog-naive-first-engine.md.

## Sprint 01

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [NFE-001](NFE-001.md) | Package scaffolding | none | done |
| [NFE-002](NFE-002.md) | Rolling-origin walk-forward splitter | NFE-001 | done |
| [NFE-003](NFE-003.md) | Configurable purge gap | NFE-002 | done |
| [NFE-004](NFE-004.md) | Baseline Strategy interface | NFE-002 | done |
| [NFE-005](NFE-005.md) | Naive0 baseline | NFE-004 | done |
| [NFE-006](NFE-006.md) | NaiveLast baseline | NFE-004 | done |
| [NFE-007](NFE-007.md) | Error metrics: MAE, RMSE | NFE-001 | done |
| [NFE-008](NFE-008.md) | Error metrics: sMAPE, MASE | NFE-001 (after NFE-007, same file) | done |
| [NFE-009](NFE-009.md) | Directional metrics: DA, F1 | NFE-001 (after NFE-008, same file) | done |
| [NFE-010](NFE-010.md) | Out-of-sample R² | NFE-001 (after NFE-009, same file) | done |
| [NFE-011](NFE-011.md) | Diebold-Mariano test core | NFE-005, NFE-007 | done |
| [NFE-012](NFE-012.md) | Harvey correction | NFE-011 | done |
| [NFE-013](NFE-013.md) | Typed result/report schema objects | NFE-003, NFE-009, NFE-012 | done |
| [NFE-014](NFE-014.md) | Template Method orchestration | NFE-005, NFE-006, NFE-013 | done |
| [NFE-015](NFE-015.md) | Regression suite (1h thesis numbers, hard gate) | NFE-014 | done (1 disclosed unmet criterion: RF/ARIMA DM counts not reconstructed) |

## Execution / parallelization plan

- **Round 0 (Tech Lead, direct)**: NFE-001 — pure scaffolding, done directly rather than delegated (no design decision to make).
- **Round 1 (parallel)**: NFE-002 (splitting branch) and NFE-007 (metrics branch, MAE/RMSE) — independent files (`splitting.py` vs `metrics.py`), no shared data.
- **Round 2 (sequential within branch, parallel across branches)**: NFE-003 (splitting, depends on NFE-002) run in parallel with NFE-008 (metrics, depends on NFE-007 same-file).
- **Round 3**: NFE-004 (baselines, depends on NFE-002/003 for `Split` shape) in parallel with NFE-009 (metrics, depends on NFE-008 same-file).
- **Round 4**: NFE-005 and NFE-006 (both depend on NFE-004, same file `baselines.py` — run **sequentially**, not parallel, to avoid two agents editing the same file at once) in parallel with NFE-010 (metrics, depends on NFE-009 same-file).
- **Round 5**: NFE-011 (depends on NFE-005 + NFE-007, both now done) — first cross-branch join.
- **Round 6**: NFE-012 (depends on NFE-011).
- **Round 7**: NFE-013 (depends on NFE-003, NFE-009, NFE-012 — all done by now).
- **Round 8**: NFE-014 (depends on NFE-005, NFE-006, NFE-013).
- **Round 9**: NFE-015 (depends on NFE-014, hard gate, run last).

Deferred to Sprint 02: NFE-016, NFE-017, NFE-018 (Should/Could priority). Not scheduled: NFE-019/020 (Won't).

## Sprint 02

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [NFE-016](NFE-016.md) | Regression suite (6h/24h thesis numbers, Harvey correction) | NFE-015 | done |
| [NFE-017](NFE-017.md) | Standalone publishability check | NFE-001 | done |
| [NFE-018](NFE-018.md) | Public API doc-sync check | NFE-014 | done |

## Execution / parallelization plan (Sprint 02)

- **Round 0 (parallel)**: NFE-016, NFE-017, NFE-018 all run in parallel — disjoint files (new test files for NFE-016; `scripts/check_standalone.*` for NFE-017; `scripts/check_doc_sync.py` + README for NFE-018), no shared data dependency, per sprint-02.md.

# services/validation-service (VS-*)

Source: docs/sprints/sprint-03.md, docs/product/backlog-validation-service.md.

## Sprint 03

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [VS-001](VS-001.md) | Service scaffolding | none | done |
| [VS-002](VS-002.md) | `validation` schema definition (`runs`, `split_results`) | VS-001 | done |
| [VS-003](VS-003.md) | Repository interfaces | VS-002 | done |
| [VS-004](VS-004.md) | Interim SQLite-backed repository implementation | VS-003 | done |
| [VS-005](VS-005.md) | `DatasetSource` abstraction + interim implementation | VS-001 | done |
| [VS-006](VS-006.md) | `POST /runs` endpoint | VS-004, VS-005 | done |
| [VS-007](VS-007.md) | `GET /runs/{id}` endpoint | VS-006 | done |
| [VS-008](VS-008.md) | `GET /runs/{id}/splits` endpoint | VS-006 | done |
| [VS-009](VS-009.md) | `run.completed` event publishing interface + interim implementation | VS-006 | done |
| [VS-011](VS-011.md) | Integration regression test: `POST /runs` round trip | VS-006, VS-008 | done |
| [VS-012](VS-012.md) | Run failure/status handling | VS-006, VS-009 | done |

VS-010 (tenant context resolution) is explicitly **blocked** on `libs/common` shipping a minimal tenant-context module (which does not exist yet — only a README) — not started this sprint, per the backlog's own decision 1. VS-013/014/015/016/017 (Should/Could) deferred to a later sprint, matching the Sprint 01→02 pattern.

## Execution / parallelization plan (Sprint 03)

- **Round 0 (Tech Lead, direct)**: VS-001 — pure scaffolding, done directly rather than delegated, same precedent as NFE-001.
- **Round 1 (parallel)**: VS-002 (schema branch, depends on VS-001) and VS-005 (`DatasetSource` branch, depends on VS-001 only) — independent files (`src/app/models.py` + `migrations/` vs `src/app/dataset_source.py`), no shared data.
- **Round 2**: VS-003 (repository interfaces, depends on VS-002).
- **Round 3**: VS-004 (SQLite repository implementation, depends on VS-003).
- **Round 4**: VS-006 (`POST /runs`, depends on VS-004 + VS-005, both done by now) — creates `src/app/routers/runs.py`.
- **Round 5**: VS-007 (`GET /runs/{id}`, depends on VS-006, edits the same `runs.py` file VS-006 created — sequential, not parallel with VS-006 or VS-009).
- **Round 6 (parallel)**: VS-008 (`GET /runs/{id}/splits`, depends on VS-006 only, deliberately placed in its own new file `src/app/routers/splits.py` to avoid overlap) and VS-009 (`run.completed` publisher, depends on VS-006, edits `runs.py`'s `POST` handler — safe in parallel with VS-008 since VS-008 never touches `runs.py`, and safe after VS-007 since VS-007's edit to `runs.py` is already merged).
- **Round 7 (parallel)**: VS-011 (integration regression test, depends on VS-006 + VS-008, adds only a new test file — no production-code overlap) and VS-012 (failure handling, depends on VS-006 + VS-009, edits `runs.py`'s exception handling — safe in parallel with VS-011 since VS-011 touches no production file).

Deferred: VS-010 (blocked, flagged for PM/Tech Lead to sequence a `libs/common` backlog). Not scheduled this sprint: VS-013/014/015/016/017 (Should/Could). Not proposed: VS-018/019/020 (Won't).

**Sprint 03 outcome**: all 11 in-scope Must stories done. `uv run pytest` (`.venv\Scripts\python.exe -m pytest -q`) passes: 48 passed, 0 failed, in `services/validation-service`. Every ticket's Review acceptance criteria were personally verified by the Tech Lead (reading the actual diff, not just trusting a green checkmark), with particular scrutiny on VS-004/VS-007/VS-008's tenant-isolation tests, VS-006's exact-as-exposed call to `run_validation_protocol`, and VS-012's structural (not merely tested) guarantee that `run.completed` cannot fire on a failed run.

## Sprint 04

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [VS-010](VS-010.md) | Tenant context resolution | `libs/common` LC-001–004 | done |

See docs/sprints/sprint-04.md. VS-010 was blocked at the end of Sprint 03 pending `libs/common`'s minimal tenant-context module; this sprint unblocks and completes it, sequenced last (after LC-001–004 land).

## Sprint 06

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [VS-013](VS-013.md) | Postgres-backed repository implementation | ARCH-001/002/004, INF-001/005 | done |
| [VS-014](VS-014.md) | Redis Streams-backed `run.completed` publisher | INF-002 | done |

See docs/sprints/sprint-06.md Phase 4. Both unblock Should stories that sat blocked since Sprint 03/04 pending real infra (this sprint's four-backlog debt sprint).

## Sprint 09

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [VS-021](VS-021.md) | Fix `PostgresValidationRunRepository.create_run`'s post-commit `session.refresh()` losing RLS's per-transaction `app.tenant_id` scope (production-breaking regression surfaced live by INF-014) | INF-014 | done |

See docs/sprints/sprint-09.md. Runs first, no dependency on anything else in Sprint 09 -- fixes a real HTTP 500 on `POST /runs` under real (non-superuser) RLS enforcement, unblocking OPS-004's own full-stack smoke test from failing on an unrelated cause. Fix mirrors `services/gateway-api`'s `PostgresTenantRepository.create_tenant`/`PostgresUserRepository.create_user` (GW-012) precedent: build the returned record from the pre-commit object instead of a post-commit `session.refresh()`. Personally verified by the Tech Lead against the real running, RLS-enforced stack (not just a unit test): `POST /runs` through `gateway-api` now returns `201` (was `500`), a direct superuser `psql` read confirms correct persistence/tenant-isolation, and both services' full suites re-run at `gateway-api` 68/68 and `validation-service` 65/65 (including the 6 previously-blocked live-Postgres tests in `test_postgres_repository.py`), matching the Sprint 08 baseline with zero regressions.

## Sprint 10

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [VS-016](VS-016.md) | OpenAPI contract / README sync check | VS-006/007/008 (done, Sprint 03) | done |

See docs/sprints/sprint-10.md. Deferred since Sprint 03 (7 sprints), pulled in on
zero-cost/zero-risk grounds. `services/validation-service/README.md`'s Contract section was
restructured to point at `/openapi.json`/`/docs` as the source of truth for exact request/response
shapes, replacing the old hand-listed field-by-field duplication -- the behavioral/design narrative
(tenant isolation, failure handling, synchronous-execution caveat) was retained under a new
`## Routes` section listing path+method only. A doc-sync check
(`services/validation-service/scripts/check_doc_sync.py` + `tests/test_doc_sync.py`) was built,
deliberately using a real `from app.main import app` introspection of the live `app.routes` (not
NFE-018's AST-parsing, which solved a different avoid-import constraint that doesn't apply to an
already-running FastAPI service) -- Tech-Lead-verified directly: the check passes against the
current repo state, a drift-detection demonstration (inject an undocumented route reference,
confirm failure, revert, confirm pass) was personally re-run, `git status` scoped to
`services/validation-service/src/app/routers/` shows zero changes, and the full suite passes 69/69
(65 Sprint 09 baseline + 4 new doc-sync tests), re-confirmed against the real Postgres/Redis
containers after the `naive-first-postgres` container (found exited at the start of this sprint's
verification pass) was restarted.

## Sprint 14

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [VS-022](VS-022.md) | Tenant-scoped `GET /runs` list endpoint | VS-003, VS-004, VS-013 (all done) | done |

See docs/sprints/sprint-14.md. Closes `DASH-005-GAP` (open since Sprint 11) -- the first half of the sprint's `VS-022 -> GW-016` chain, run in parallel with `INF-018` (infra). Adds `RunSummaryResponse` to `libs/common/src/naive_first_common/contracts.py` (the single canonical definition, reused by `GW-016`, not redefined) and a new `list_runs` method on `ValidationRunRepository`, implemented by both the SQLite (VS-004) and Postgres (VS-013) backends without changing either's existing `create_run`/`get_run`/`update_run_status` call sites. The hard server-side `limit` ceiling (max 100, `422` on out-of-range, never clamped) and the non-tautological cross-tenant test (asserts by id, not just count) received the sprint's own flagged extra review scrutiny. `services/validation-service/README.md`'s Routes section gains `GET /runs`; VS-016's doc-sync check re-run and confirmed still passing.
**Sprint 14 outcome (validation-service)**: `87 passed`, 0 failed, `1833.57s` (0:30:33), personally re-run by the Tech Lead against the real Postgres/Redis containers -- zero regressions.

# libs/common (LC-*)

Source: docs/sprints/sprint-04.md, docs/product/backlog-libs-common.md.

## Sprint 04

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [LC-001](LC-001.md) | Package scaffolding | none | done |
| [LC-002](LC-002.md) | `TenantContext` typed value object | LC-001 | done |
| [LC-003](LC-003.md) | FastAPI `Depends()`-based tenant context resolver (interim: explicit-field extraction) | LC-002 | done |
| [LC-004](LC-004.md) | Fail-closed test suite for tenant context resolution | LC-003 | done |

## Execution / parallelization plan (Sprint 04)

Strictly sequential, no parallelization: LC-001 -> LC-002 -> LC-003 -> LC-004 -> VS-010 (tracked above under validation-service). Each story depends on the previous existing (package skeleton -> typed shape -> resolver returning that shape -> tests proving the resolver -> the one real consumer wiring it in), per sprint-04.md's own stated execution order — this is a small sprint with no independent branches to run in parallel, unlike Sprint 01-03.

Deferred: LC-005 (README doc-sync), LC-006 (shared schemas), LC-007 (DB session helpers), LC-008 (formatting logic), LC-009 (JWT/API-key resolution) — all Should/Won't this backlog, per sprint-04.md's explicit deferral list.

## Sprint 10

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [LC-005](LC-005.md) | README status update + public API doc-sync | LC-003 (done, Sprint 04) | done |

See docs/sprints/sprint-10.md. Longest-standing deferred item in the platform (Sprint 04 -> 10, 6
sprints), pulled in on zero-cost/zero-risk/zero-dependency grounds. `libs/common/README.md`'s status
line reconciles the backlog's now-stale "tenant-context module only" wording against the real,
already-shipped ARCH-001/002/003/004 additions (`build_engine`/`contracts`/`testing`), explicitly
listing `TenantContext`/`get_tenant_context` and distinguishing shipped vs. not-yet-shipped scope.
A doc-sync check (`libs/common/scripts/check_doc_sync.py` + `libs/common/tests/test_doc_sync.py`)
was built mirroring `naive_first_engine`'s NFE-018 precedent in structure (not literal code).
Tech-Lead-verified directly: the check passes against the current repo state, a drift-detection
demonstration (inject an undocumented function, confirm failure, revert, confirm pass) was
personally re-run, and the full `libs/common` suite passes 21/21 (20 pre-existing + 1 new).

## Sprint 10 — ARCH-* (docs/product/backlog-technical-upgrades.md)

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [ARCH-007](ARCH-007.md) | Protocol-agnostic service-identification convention | none | done |
| [ARCH-008](ARCH-008.md) | Document the `Security()`/`APIKeyHeader` auth pattern as the required shape | none | done |

See docs/sprints/sprint-10.md. Both Should-priority, deferred since Sprint 06, re-confirmed
unchanged in Sprints 07/08/09 ("codebase shape hasn't grown"), pulled into Sprint 10 on
zero-cost/zero-risk/zero-dependency grounds. Both are pure documentation against
`services/gateway-api/README.md` (ARCH-007 also adds a short pointer bullet to
`docs/implementation-plan.md` section 9) -- zero files under `services/gateway-api/src/` touched by
either ticket, confirmed via `git status` scoped to that path both before and after each ticket
(the path's pre-existing, unrelated-session modifications were left untouched throughout).
**ARCH-007**: documents the REST tagging convention (`tags=["<service-name>"]`, citing the real
`runs.router` -> `"validation-service"` instance) plus forward-looking gRPC/GraphQL naming rules, with
no contradiction of implementation-plan.md section 4's "not using gRPC/GraphQL yet" stance (Tech
Lead re-read both directly). **ARCH-008**: extends the Authentication (GW-006) section with a
forward-looking requirement that any future header-based auth dependency use `Security()` + a
`fastapi.security` class (never bare `Header()`), citing `auth.py`'s `_authorization_scheme`/
`_x_api_key_scheme` as the reference implementation; `tests/test_auth.py`'s 11 cases re-run directly
by the Tech Lead, unchanged.

## Sprint 06 — ARCH-* (docs/product/backlog-technical-upgrades.md)

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [ARCH-001](ARCH-001.md) | Extract duplicated SQLite engine-building scaffolding into libs/common | none | done |
| [ARCH-002](ARCH-002.md) | Fix per-request DB engine instantiation (memoize once per process, keyed by URL) | ARCH-001 | done |
| [ARCH-004](ARCH-004.md) | Extract duplicated SQLite test-fixture into shared test-utility | none (bundled with ARCH-001) | done |
| [ARCH-003](ARCH-003.md) | Move gateway-api proxy wire-contract into shared libs/common package | none | done |

See docs/sprints/sprint-06.md Phase 1, Track A. A prior grooming session produced 10 binding decisions (see sprint-06.md task framing / each ticket's Design section) that these four tickets carry as given facts. ARCH-002 is the sprint's single highest cross-service regression risk (per-request engine construction fix touching both services' DI wiring). Deferred: ARCH-005 (Should, tracking story), ARCH-006 (Won't), ARCH-007 (Should, tracking story — added 2026-08-09, protocol-agnostic service-identification convention; not yet scheduled to a sprint), ARCH-008 (Should, tracking story — added 2026-08-09, document the `Security()`/`APIKeyHeader` auth pattern; not yet scheduled to a sprint).

# services/gateway-api (GW-*)

Source: docs/sprints/sprint-05.md, docs/product/backlog-gateway-api.md.

## Sprint 05

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [GW-001](GW-001.md) | Service scaffolding | none | done |
| [GW-002](GW-002.md) | `identity` schema definition (`tenants`, `users`, `api_keys`) | GW-001 | done |
| [GW-003](GW-003.md) | Identity repository interfaces | GW-002 | done |
| [GW-004](GW-004.md) | SQLite-backed repository implementation (interim) | GW-003 | done |
| [GW-005](GW-005.md) | Tenant + API-key provisioning (operator-facing) | GW-004 | done |
| [GW-006](GW-006.md) | API-key authentication | GW-005 | done |
| [GW-007](GW-007.md) | Verified `TenantContext` resolution + downstream forwarding | GW-006 | done |
| [GW-008](GW-008.md) | Request routing to validation-service's real endpoints | GW-007 | done |
| [GW-009](GW-009.md) | Downstream failure handling (timeouts, connection errors) | GW-008 | done |

## Execution / parallelization plan (Sprint 05)

Strictly sequential, no parallelization opportunity — sprint-05.md's own dependency chain confirms each story's sole predecessor is the story immediately before it, unlike Sprint 01/03's independent branches. GW-001 scaffolded directly by the Tech Lead (no design decision to delegate, same precedent as NFE-001/VS-001/LC-001); GW-002 through GW-009 delegated one at a time to a dev subagent, each verified against the actual diff before the next is started. GW-006 (auth) and GW-007 (tenant forwarding) receive additional personal verification per the sprint's extra-sensitive-ticket instruction (SHA-256 hashing / never-plaintext / never-logged for GW-006; zero `libs/common`/`validation-service` changes and verified-tenant-only forwarding for GW-007).

Deferred: GW-010 through GW-014 (Should/Could). Not started: GW-015 (Won't, this backlog — explicitly `libs/common`'s LC-009 concern).

## Sprint 06

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [GW-012](GW-012.md) | Postgres-backed identity repository + row-level security | ARCH-001/002/004, INF-001/005 | done |

See docs/sprints/sprint-06.md Phase 4. Sprint 06's second extra-sensitive ticket (alongside ARCH-002) — RLS `SET LOCAL` tenant-scoping hook must fire on every pooled-connection checkout, not just once at startup. **Follow-up flagged, not silently accepted**: see INF-014 below — the Postgres role both services actually connect as is a superuser (`BYPASSRLS`), so RLS policies are correctly written and proven-in-test but currently unenforced against real deployed credentials.

## Sprint 14

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [GW-016](GW-016.md) | Proxy route for validation-service's `GET /runs` list endpoint | VS-022 (this sprint), GW-007, GW-009 (done) | done |
| [GW-018](GW-018.md) | Proxy routes for reporting-service's `POST /reports/generate` / `GET /reports/{id}` | reporting-service's RS-004/RS-005 (done), GW-007, GW-009 (done) | done |

See docs/sprints/sprint-14.md. `GW-016` closes the second, symmetric half of `DASH-005-GAP` (`VS-022` is the first) -- runs after `VS-022` lands. `GW-018` closes the `gateway-api` half of `RS-GAP` (paired with `INF-018`) -- run strictly after `GW-016` completes and its diff is personally verified by the Tech Lead, not in parallel, per the sprint's own binding same-file-collision-avoidance instruction (both tickets touch the router layer and README Contract section). `GW-016` reuses `VS-022`'s new `RunSummaryResponse` from `naive_first_common.contracts`; `GW-018` adds a new `REPORTING_SERVICE_URL` env var and a new `reports.py` router module (disjoint from `runs.py`, zero file overlap with `GW-016`). Both reuse GW-009's existing timeout/failure handling unmodified. `GW-018`'s own documentation restates the sprint's disclosed caveat: only the manual `POST /reports/generate` -> `GET /reports/{id}` flow is reachable end-to-end through `gateway-api` after this sprint -- the automatic `run.completed`-triggered flow (`RS-006`) remains `todo` in Sprint 12, a gap in `RS-006`, not a `GW-018` defect.
**Sprint 14 outcome (gateway-api)**: `GW-016` personally re-run by the Tech Lead -- `72 passed`, 0 failed, `393.26s`. `GW-018` personally re-run by the Tech Lead after `GW-016` -- `80 passed`, 0 failed, `393.04s`. Both confirmed zero file overlap in `runs.py` (byte-for-byte identical diff before/after `GW-018`).

# infra (INF-*)

Source: docs/sprints/sprint-06.md, docs/product/backlog-infra.md.

## Sprint 06

| Ticket | Story | Phase | Depends on | Status |
|---|---|---|---|---|
| [INF-001](INF-001.md) | PostgreSQL + TimescaleDB service in Docker Compose (one DB, two schemas: validation + identity) | 1 (Track B) | none | done |
| [INF-002](INF-002.md) | Redis service in Docker Compose | 1 (Track B) | none | done |
| [INF-003](INF-003.md) | validation-service wired into Docker Compose | 2 | INF-001, INF-002 | done |
| [INF-004](INF-004.md) | gateway-api wired into Docker Compose | 2 | INF-001, INF-003 | done |
| [INF-005](INF-005.md) | Verify both services' Alembic migrations run against Compose Postgres | 2 | INF-001, INF-003, INF-004 | done, with one finding reported (unresolved cross-service `alembic_version` collision — resolved by VS-013/GW-012's `version_table_schema` work, see those tickets) |
| [INF-006](INF-006.md) | Persistent volumes for Postgres and Redis | 3 | INF-001, INF-002 | done |
| [INF-007](INF-007.md) | infra/README.md and .env.example reflect actual, built state | 3 | INF-001–006 | done |

Deferred: INF-008 (MinIO, Should), INF-009 (healthchecks/startup ordering, Should), INF-010 (TimescaleDB hypertables, Could). Not started: INF-011/012/013 (Won't, this backlog).

**Follow-up surfaced during Sprint 06, now a real ticket**: the informal flag below (a Postgres
superuser role connecting the app, bypassing RLS unconditionally) is scheduled and executed as
**INF-014** in Sprint 07 — see that section below, not left informal any longer.

## Sprint 07

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [INF-014](INF-014.md) | Non-superuser Postgres application role for validation-service/gateway-api | INF-001, VS-013, GW-012 | done (1 disclosed, out-of-scope finding — see below) |
| [INF-016](INF-016.md) | Repeatable "apply new migrations" command (`infra/migrate.sh`/`.ps1`) | INF-005 | done |
| [INF-015](INF-015.md) | First-boot bootstrap script (`infra/bootstrap.sh`/`.ps1`) | INF-001–005, INF-014, INF-016 | done |

See docs/sprints/sprint-07.md for the full sequencing decision (INF-014 → INF-016 → INF-015, not
their numeric order) and docs/product/backlog-infra.md's Post-Sprint-06 additions section for all
three stories' full text. INF-017 (DB-backed operator/tenant configuration) is explicitly deferred,
not scheduled this sprint or any future one until a concrete per-tenant/per-operator behavior
difference is identified (see backlog-infra.md INF-017 for the full recorded decision).

**Sprint 07 outcome**: all 3 in-scope stories done, executed in the sequencing decision's order
(INF-014 → INF-016 → INF-015), each personally re-verified by the Tech Lead against the real,
live `infra/docker-compose.yml` stack (Docker Desktop was found not running at the start of this
sprint's execution and was started; the existing `naive-first-postgres` container/volume from
Sprint 06 was brought back up, not recreated from empty, so the fresh-volume-only init script did
not silently re-run and mask a real live-container gap). **INF-014**: `naive_first_app`
(`NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`, scoped to `SELECT`/`INSERT`/`UPDATE`/`DELETE`
on `validation.*`/`identity.*` only) confirmed live on the running container; `naive_first`
repurposed migration-only; both app containers reconnected without a crash-loop; both services'
full suites pass (`gateway-api` 68/68, `validation-service` 65/65). DB-level RLS enforcement was
proven directly, not merely asserted: connected as the real runtime role `naive_first_app` via
`psql` and ran a raw, **unfiltered** query (no `WHERE tenant_id = ...` clause at all) under
different `set_config('app.tenant_id', ...)` scopes — Tenant A's row was visible only under its own
scope and invisible (0 rows) under Tenant B's scope or an unset scope, proving Postgres RLS itself
is the isolation mechanism, independent of any application-level filter. Also independently
confirmed at the application layer: `GET /runs/{id}` through the real running `gateway-api` returns
`200` for the owning tenant and `404` for a different tenant's key on the same run id. **One real,
disclosed, NOT silently patched finding**: `POST /runs` on `validation-service`'s Postgres-backed
`create_run` now returns `500` under genuine RLS enforcement (previously masked by the superuser
role's unconditional RLS bypass) — root cause is a `session.refresh()` call issued *after*
`commit()`, in a new transaction that never re-establishes the per-transaction `app.tenant_id`
scope, so RLS correctly (if surprisingly) hides the just-inserted row from the refresh's own
`SELECT`. The row itself is correctly persisted and correctly tenant-isolated (confirmed via direct
superuser read) — this is a response-construction bug, not a data-loss or isolation bug.
`gateway-api`'s own `PostgresTenantRepository.create_tenant`/`PostgresUserRepository.create_user`
(GW-012) already document and avoid this exact pitfall by building the returned record from the
pre-commit object instead of calling `session.refresh()`; `validation-service`'s `create_run` did
not follow that same precedent. **This is flagged as a new, real, production-breaking regression
requiring its own follow-up ticket against `services/validation-service`** (out of INF-014's own
scope, which forbids `services/*/src/` changes) — recommended fix: mirror `gateway-api`'s
pre-commit-record pattern. Not actioned in this sprint; escalated to the requester, not deferred
silently. **INF-016**: `infra/migrate.sh`/`infra/migrate.ps1` built, single source of the
`alembic upgrade head` invocation (grep-confirmed no duplicate elsewhere in `infra/`), always uses
the migration-time `naive_first` role; `migrate.ps1` personally re-run twice against the live stack
by the Tech Lead (idempotent, no-op at head both times) in addition to the dev agent's own two
runs; `migrate.sh`'s `alembic upgrade head` code path could not be exercised end-to-end on this
Windows host (POSIX `.venv/bin/python` layout vs. this environment's Windows `.venv\Scripts\
python.exe`) — accepted as a disclosed, non-blocking environment limitation, not a defect (the
script's argument-validation and fail-loud paths were still exercised for real). **INF-015**:
`infra/bootstrap.sh`/`infra/bootstrap.ps1` built as pure orchestration, delegating migrations
entirely to INF-016's script; `bootstrap.ps1` personally re-run end-to-end by the Tech Lead (all
five steps, real output, stack left healthy); a genuine step-3 failure (same POSIX/Windows `.venv`
mismatch as `migrate.sh`) doubled as the required real failure-path proof for `bootstrap.sh`, and a
separate isolated real test proved step 2's bounded health-wait also fails loudly and stops the
script rather than continuing. The script never auto-runs `provision_tenant.py` — it prints the
exact, copy-paste-correct containerized invocation, verified by actually running the printed
command and confirming it provisions a real tenant against the just-started `gateway-api`
container. Documentation acceptance criteria for all three tickets confirmed: `infra/README.md` now
leads with `bootstrap.sh`/`bootstrap.ps1` as the recommended first-boot path (prior hand-run
sequence kept underneath, not deleted) and documents the two-role split and the migrate script;
`services/gateway-api/README.md`'s "Known infra caveat" paragraph now states the RLS-enforcement
gap is resolved, pointing at INF-014. No file under `services/validation-service/src/` or
`services/gateway-api/src/` was changed by any of the three tickets (confirmed via `git status`
scoped to those paths after each ticket).

**Sprint 05 outcome**: all 9 in-scope Must stories done. `.venv\Scripts\python.exe -m pytest -q` in `services/gateway-api` passes 55/55 (0 failures), including GW-004's revoked-key-still-resolves test, GW-006's full valid/missing/malformed/unknown/revoked auth coverage, GW-007's spoofed-inbound-header proof, GW-008's cross-tenant `404` tests, and GW-009's timeout/connection-refused/status:"failed"-pass-through tests. Zero regressions confirmed by re-running both other suites after the sprint: `services/validation-service` 51/51, `libs/common` 14/14 (both unchanged from Sprint 04's baseline). GW-001 was scaffolded directly by the Tech Lead (no design decision to delegate, same precedent as NFE-001/VS-001/LC-001); GW-002 through GW-009 were each delegated to a dev subagent and personally verified by the Tech Lead by reading the actual diff (not just trusting the agent's self-report) before being marked done. GW-006 (auth) and GW-007 (tenant forwarding) received the sprint's mandated extra scrutiny: GW-006 confirmed to hash exclusively with `hashlib.sha256`, compare only hash-to-hash (never plaintext), and never log/print the presented raw key anywhere; GW-007 confirmed via a direct `git status` scope check to touch zero files under `libs/common/` or `services/validation-service/`, and confirmed structurally (not just behaviorally) that `build_downstream_headers` cannot read the inbound request's own `X-Tenant-Id` header. No deviations from sprint-05.md's binding note: SHA-256 used throughout, never bcrypt/argon2/scrypt.

**Sprint 04 outcome**: all 4 in-scope `libs/common` Must stories (LC-001–004) plus VS-010 done, matching sprint-04.md's Definition of Done. `libs/common`: `.venv\Scripts\python.exe -m pytest -q` passes 14/14 (LC-002/003 unit tests + LC-004's standalone fail-closed app-level suite). `services/validation-service`: `.venv\Scripts\python.exe -m pytest -q` passes 51/51 (48 pre-existing Sprint 03 tests, now exercising `Depends(get_tenant_context)` instead of the interim field, plus 3 new VS-010 fail-closed-before-repository tests). Both READMEs updated (`libs/common` status "scaffolded"; `services/validation-service` Contract section documents the `X-Tenant-Id` header replacing the retired `tenant_id` body/query field). LC-001 was scaffolded directly by the Tech Lead (no design decision to delegate, same precedent as NFE-001/VS-001); LC-002/003/004/VS-010 were each delegated to a dev subagent and personally verified by the Tech Lead by reading the actual diff (not just trusting the agent's self-report) before being marked done — VS-010 in particular was checked for: `Depends(get_tenant_context)` imported unmodified from `naive_first_common` with no local reimplementation, the interim `tenant_id` field/params fully removed (not left dead), tenant-isolation logic unchanged apart from the source of `tenant_id`, and the new fail-closed test's non-tautological proof (a repository fake that fails the test if reached) run directly by the Tech Lead. No deviations from sprint-04.md's binding notes: 401 (not 400) used throughout LC-003/LC-004/VS-010; LC-001 never touched `services/validation-service/pyproject.toml`; VS-010 was the ticket that added `naive_first_common` to that file. No code outside `libs/common`/`services/validation-service` was touched.

**Sprint 06 outcome**: all 14 in-scope stories (ARCH-001/002/003/004, INF-001–007, VS-013, VS-014, GW-012) done, matching sprint-06.md's Definition of Done. All 4 modules' full suites pass with zero regressions, verified directly by the Tech Lead: `libs/naive_first_engine` 94/94 (untouched, sanity baseline), `libs/common` 20/20, `services/validation-service` 63/63, `services/gateway-api` 66/66. A real Postgres+TimescaleDB and Redis are running in `infra/docker-compose.yml` alongside real, containerized `validation-service`/`gateway-api`; a full-stack smoke test (provision tenant -> `POST /runs` through `gateway-api` -> proxied to `validation-service` -> real `naive_first_engine` execution -> persisted results -> proxied back) was executed for real, not simulated, during INF-004. All 10 grooming-session binding decisions were implemented as specified, not merely referenced (see the full confirmation checklist in the Tech Lead's sprint report to "main"). One real, load-bearing finding from INF-005 (both services' migrations collide on a shared `public.alembic_version` if neither schema-qualifies its version table) was caught, escalated into a hard requirement on VS-013/GW-012 (rather than left as the original ticket's "should"), and confirmed fixed by rerunning both services' full suites together. One new gap was surfaced and deliberately NOT silently patched: the Postgres role both services actually connect as (`naive_first`, provisioned by INF-001) is a superuser, which Postgres unconditionally exempts from RLS — VS-013's and GW-012's RLS policies are correctly authored and proven against a purpose-built non-superuser test role, but are not yet enforced against the real running credentials. Tracked as a new follow-up (INF-014, proposed, not yet scheduled) rather than counted as "done" in this sprint's RLS acceptance criteria. Round 2's ARCH-002 (memoization keyed by URL, not zero-arg) and GW-012 (SET LOCAL firing per-transaction, not once at startup, proven via a `pool_size=1`/`pg_backend_pid()` pooled-connection-reuse test) received the sprint's mandated extra scrutiny, both personally verified by the Tech Lead reading the actual code and diff, not just trusting a green checkmark.

## Sprint 14

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [INF-018](INF-018.md) | `reporting-service` wired into Docker Compose as a real, runnable container | INF-001, INF-002, INF-014, reporting-service's RS-001/RS-002 (all done) | done |

See docs/sprints/sprint-14.md. Closes the infra half of `RS-GAP` (paired with `GW-018`), run in parallel with `VS-022` from the start of the sprint -- genuinely independent, disjoint files (`infra/docker-compose.yml` + `services/reporting-service/Dockerfile` vs. `services/validation-service/`). Packaging/wiring only -- zero changes under `services/reporting-service/src/`, confirmed via `git status` scoped to that path before and after. `DATABASE_URL` uses the existing non-superuser `naive_first_app` role (INF-014), not `naive_first` -- does not reintroduce the RLS-bypass gap that role was created to close. Verified against the real, live Compose stack, not merely a config-file review: `docker compose up reporting-service` succeeds, `POST /reports/generate`/`GET /reports/{id}` respond over the container's exposed port. `infra/README.md`'s "not yet wired into compose" statement updated to remove `reporting-service`, cross-referencing `GW-018` as the other `RS-GAP` half needed for actual reachability from outside the Docker network.
**Sprint 14 outcome (infra)**: live-stack verification personally performed by the Tech Lead (not merely re-read from the dev agent's report) -- `docker compose build/up reporting-service` succeeded, `GET /health` returned `200`, a real `POST /reports/generate` -> `GET /reports/{id}` round trip was independently reproduced with real HTTP responses, and `naive_first_app` (not `naive_first`) was confirmed as the live runtime role via `pg_stat_activity`. One real, disclosed gap found and fixed: the `reporting` Postgres schema/grants, previously only hand-applied to the long-lived Sprint 06+ container, are now in `infra/postgres-init/` so a fresh volume gets them automatically too.

# Operability (OPS-*)

Source: docs/product/backlog-operability.md. Cross-cutting backlog (spans all five shipped modules plus `infra`), covering CONTEXT.md's Operability definition — maintainability (dependency upgrades, doc-sync checks, test-coverage gaps) and runtime observability (logs, metrics, health checks, alerting) — not yet split into two backlogs, per that glossary entry's own instruction. Proposed 2026-08-10. ARCH-005/LC-009 (unverified tenant header) is deliberately *not* duplicated here — it stays solely under `libs/common (LC-*)` above as a security/authentication gap, not an Operability one; see backlog-operability.md's own stated scope decision.

## Sprint 08

| Ticket | Story | Module(s) | Depends on | Status |
|---|---|---|---|---|
| [OPS-001](OPS-001.md) | Automated CI pipeline running every module's test suite (incl. NFE-015/016 regression gate, NFE-018 doc-sync check) | root (`.github/workflows/`) + all 5 module READMEs | none | done |
| [OPS-005-01](OPS-005-01.md) | Deepen validation-service's `/health` to check real DB connectivity | services/validation-service | none | done |
| [OPS-005-02](OPS-005-02.md) | Deepen gateway-api's `/health` to check real DB connectivity | services/gateway-api | none | done |
| [OPS-002](OPS-002.md) | Measure and report test coverage in CI (no hard gate) | root CI file + all 5 modules | OPS-001 | done |
| [OPS-003](OPS-003.md) | Documented dependency-upgrade cadence/policy across five modules | root docs/ + all 5 module READMEs | none (soft: OPS-001) | done |

See docs/sprints/sprint-08.md for the full sequencing decision (OPS-001 + OPS-005-01 + OPS-005-02 in parallel, then OPS-002, then OPS-003) and the explicit deferral reasoning for OPS-004 (Must, blocked in practice on Sprint 07's INF-014 completing — `infra/docker-compose.yml` already points runtime `DATABASE_URL` at the not-yet-fully-provisioned `naive_first_app` role), OPS-006 (Could, no current trigger), and OPS-007 (Won't, Product Owner decline already recorded). Also deferred, as a block, not part of this sprint: LC-005, GW-010/011/013/014, VS-016/017, INF-008/010, ARCH-005/007/008 (GW-012 already done, Sprint 06 — corrected out of the deferred list). INF-009 is flagged as likely already satisfied by `infra/docker-compose.yml`'s current in-flight state but is left for Sprint 07's own close-out to verify, not claimed here. OPS-005 was split into two tickets (OPS-005-01/02, one per service) at ticket-breakdown time since each touches exactly one service's own files — no change to the sprint's sequencing (both still run fully parallel to OPS-001 and to each other).

## Execution / parallelization plan (Sprint 08)

**Sprint 08 outcome**: all 4 in-scope stories (OPS-005-01, OPS-005-02, OPS-002, OPS-003) done,
alongside OPS-001 (already done at the start of this session). Executed in the sequencing decision's
order (OPS-001 + OPS-005-01 + OPS-005-02 in parallel -> OPS-002 -> OPS-003), each personally
re-verified by the Tech Lead against the actual diff/files, not merely trusted from the dev agents'
own outcome notes (which were themselves already present in the working tree from a prior session
and independently re-checked here rather than assumed correct). **OPS-005-01/02**: confirmed
`services/validation-service/src/app/main.py` and `services/gateway-api/src/app/main.py`'s
`/health` handlers both take `HealthCheckEngineDep`, run `SELECT 1` via `engine.connect()`, return
`200 {"status": "ok"}` unchanged on success or `503 {"status": "unhealthy", "detail": "database
unreachable"}` (fixed generic string, no raw exception/connection-string/credential leakage) on
failure; both `dependencies/repositories.py` providers reuse the existing URL-resolution helpers,
no third derivation; both services' `tests/test_health.py` exist with non-tautological
healthy/failure-path cases. **OPS-002**: `.github/workflows/ci.yml` confirmed to run all five
modules' test suites with `--cov=<package> --cov-report=term-missing`, zero occurrences of
`--cov-fail-under`/equivalent hard gate anywhere in the file (grep-confirmed); `pytest-cov>=7.1.0`
confirmed present in all four `uv`-managed modules' `pyproject.toml` dev-dependency groups;
`services/ingestion-service/requirements.txt` confirmed untouched (only its README's documented
`pip install` step changed). **OPS-003**: `docs/dependency-upgrade-policy.md` confirmed to make an
explicit decision on both open questions (manual once-per-sprint cadence, not automated; explicit
"ingestion-service unpinned floors, stays as-is, named future gap"); confirmed referenced from all
five modules' own READMEs via a "Dependency upgrades" line placed after each README's OPS-002
"Coverage" line; confirmed documentation-only (no `src/`, `pyproject.toml`, `requirements.txt`, or
`uv.lock` touched by this ticket specifically). OPS-003's own Review acceptance-criteria checkboxes
(previously left unchecked by the dev agent, per its own Outcome note stating Tech Lead verification
was pending) are now checked and its status moved from `todo` to `done`.

**Full test suites re-run directly by the Tech Lead** (not merely trusted from OPS-002's own
recorded run): `services/gateway-api` — `.venv\Scripts\python.exe -m pytest -q` → **68 passed**, 0
failed, 393.16s; `services/validation-service` — `.venv\Scripts\python.exe -m pytest -q` → **65
passed**, 0 failed, 1310.37s (0:21:50, against the real Postgres/Redis containers). Both counts match
OPS-002's own recorded baseline exactly — zero regressions from this sprint's four tickets, confirmed
independently rather than assumed from a green checkmark. `libs/naive_first_engine` and `libs/common`
were not touched by any Sprint 08 ticket's code (only their READMEs, for OPS-002's Coverage line and
OPS-003's Dependency-upgrades line) and were not re-run in full this sprint; OPS-002's own Outcome
section already recorded their coverage-enabled runs (94/94 and 20/20 respectively) earlier in this
session.

**OPS-004 status, checked against INF-014's actual ticket file (not assumed from the index's prose)**:
`docs/tickets/INF-014.md`'s own Status line and Outcome section confirm it is `done` — the live,
already-running `naive-first-postgres` container was verified to have `naive_first_app`
(`NOSUPERUSER NOBYPASSRLS NOCREATEDB NOCREATEROLE`) as both services' runtime `DATABASE_URL` role,
both app containers reconnected cleanly, and DB-level RLS enforcement was proven directly (an
unfiltered raw query as `naive_first_app` returns only the calling tenant's rows). Per
`docs/sprints/sprint-08.md`'s own stated revisit trigger ("as soon as Sprint 07's INF-014 is
confirmed done... schedule OPS-004 immediately after, ideally as the first story of Sprint 09"),
**OPS-004 is now unblocked** and should be scheduled as Sprint 09's first story — not actioned in
this sprint (out of Sprint 08's own scope, which is OPS-001/002/003/005 only). One caveat carried
forward, not newly discovered here: INF-014's own Outcome discloses a real, production-breaking
finding — `POST /runs` on `validation-service`'s Postgres-backed `create_run` returns `500` under
genuine RLS enforcement (a post-commit `session.refresh()` issuing a new transaction that never
re-establishes `app.tenant_id`, unlike `gateway-api`'s own `create_tenant`/`create_user`, which
build the returned record from the pre-commit object instead) — this is a separate, not-yet-ticketed
bug against `services/validation-service`, independent of OPS-004's own Dockerfile/port-binding
verification scope, and should be scheduled alongside or before OPS-004, since OPS-004's own
full-stack smoke test (`POST /runs` through the real stack) would otherwise fail on this exact bug.


- **Round 1 (parallel)**: OPS-001 (new `.github/workflows/ci.yml` + all 5 READMEs' CI pointer),
  OPS-005-01 (`services/validation-service/src/app/main.py` + `dependencies/repositories.py`), and
  OPS-005-02 (`services/gateway-api/src/app/main.py` + `dependencies/repositories.py`) — three
  disjoint file sets, no dependency between any pair, per sprint-08.md's own sequencing decision.
- **Round 2**: OPS-002 (depends on OPS-001's `.github/workflows/ci.yml` existing to extend).
- **Round 3**: OPS-003 (no formal dependency, sequenced last so its "is Dependabot viable" question
  is answered by OPS-001's now-existing CI rather than left open).

## Sprint 09

| Ticket | Story | Module(s) | Depends on | Status |
|---|---|---|---|---|
| [VS-021](VS-021.md) | Fix `PostgresValidationRunRepository.create_run`'s post-commit `session.refresh()` losing RLS scope | services/validation-service | INF-014 | done |
| OPS-004 | Verify `docker compose build`/`up` still succeeds end-to-end, full-stack smoke test | infra | VS-021 (in practice, not formally) | done |

See docs/sprints/sprint-09.md. Sequencing: VS-021 first (self-contained, no dependency on anything else in this sprint, and the concrete blocker for OPS-004's own smoke test passing for the right reason), then OPS-004 -- deliberately reversing Sprint 08's own "OPS-004 as first story" suggestion, since OPS-004's own third acceptance criterion (a real `POST /runs` through the full stack) would otherwise hit VS-021's then-still-open bug and produce a false-negative result unrelated to what OPS-004 actually tests (non-root Dockerfile/port-binding correctness).

**Sprint 09 outcome**: both in-scope stories done, executed in sequence (VS-021 -> OPS-004), each
personally verified by the Tech Lead against the real, live Docker Compose stack -- not merely
trusted from the dev agent's own report. **VS-021**: `PostgresValidationRunRepository.create_run`
no longer calls `session.refresh()` after `commit()`; the returned `RunRecord` is built from the
already-fully-populated pre-commit object instead, mirroring `services/gateway-api`'s
`PostgresTenantRepository.create_tenant`/`PostgresUserRepository.create_user` (GW-012) precedent
exactly. Live RLS proof: `POST /runs` through `gateway-api` against the real, non-superuser-RLS-
enforced stack now returns `201` (previously `500`, per INF-014's Outcome), the created row was
independently confirmed via a direct superuser `psql` read, and `GET /runs/{id}` returns `200`.
**OPS-004**: `docker compose -f infra/docker-compose.yml build validation-service gateway-api`
succeeded; `docker compose -f infra/docker-compose.yml up -d` (full stack) succeeded, all four
containers (`postgres`, `redis`, `validation-service`, `gateway-api`) up and healthy; both
services' `/health` returned `200 {"status":"ok"}` from the host; the full-stack smoke test
(provision a tenant, `POST /runs` through `gateway-api`) was re-run cleanly against a freshly
provisioned tenant and returned `201` -- confirming the non-root Dockerfile/port-binding changes
from the prior session did not break `provision_tenant.py` or container startup, this time
exercising only what OPS-004 itself tests, with VS-021's RLS bug already fixed. Both services'
full test suites re-run in full and matched the Sprint 08 baseline exactly with zero regressions:
`gateway-api` 68/68, `validation-service` 65/65 (including the 6 live-Postgres tests in
`test_postgres_repository.py`, which required working around a pre-existing, unrelated local-machine
IPv6-loopback DNS-resolution quirk via the standard `PGCONNECT_TIMEOUT` libpq environment variable --
no code or test-file change -- to get a real, complete pass count instead of leaving it unverified).

# services/ingestion-service (INGEST-*)

Source: docs/tickets/INGEST-001.md, docs/product/backlog-operability.md.

## Sprint 10

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [INGEST-001](INGEST-001.md) | Retroactive ticket/SDLC tracking for already-shipped connector code | none | done |

**Not a new-feature story.** `services/ingestion-service`'s connectors (`connectors/base.py`,
`connectors/binance_price.py`, `connectors/blockchain_onchain.py`, `connectors/reddit_sentiment.py`)
and the raw-zone archive (`data/raw/_platform/PROVENANCE.md`) were built 2026-08-05 at explicit user
request, ahead of implementation-plan.md's trigger #6 (FastAPI upload API / `ingestion` Postgres
schema / data-quality gate, still unfired) -- deliberately pulling trigger #10 (market/sentiment
connectors) forward independent of the service's own HTTP wrapper. A 19-test suite
(`tests/test_base.py`, `tests/test_binance_price.py`, `tests/test_blockchain_onchain.py`,
`tests/test_reddit_sentiment.py`) was added 2026-08-09. Both were disclosed in the service's own
README from the start, but no `INGEST-*` ticket section existed in this index until now -- a real,
disclosed process gap (code shipped outside the normal PM -> Tech Lead -> dev-squad flow), matching
this repo's own precedent for `gateway-api` building ahead of trigger #5 (already ticketed under
GW-*). INGEST-001 closes that gap retroactively: it adds no source code and authorizes no new
engineering scope -- the FastAPI app, `ingestion` Postgres schema, upload API, and data-quality gate
remain gated on trigger #6, unfired. **Verification performed for this ticket**:
`.venv/Scripts/python.exe -m pytest tests/ -q` in `services/ingestion-service` re-run directly,
confirming **19 passed**, 0 failed (matches the README's own claim, independently confirmed rather
than copied). `services/ingestion-service/README.md` was re-read against the real `connectors/`/
`tests/` state (connector class names `BinancePriceConnector`, `BlockchainInfoConnector`,
`RedditSentimentConnector`, and the 19-test count) and found already accurate -- no drift, no edit
needed. `git status` scoped to `services/ingestion-service/connectors/` and
`services/ingestion-service/tests/` after this ticket shows no changes introduced by this ticket
(pre-existing uncommitted modifications to `connectors/*.py` from a prior, unrelated session were
present before this ticket started and were left untouched, not authored or altered here).

# services/dashboard-web (DASH-*)

Source: docs/sprints/sprint-11.md, docs/product/backlog-dashboard-web.md.

## Sprint 11

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [DASH-001](DASH-001.md) | Service scaffolding | none | done |
| [DASH-002](DASH-002.md) | Login screen (API key -> server-side session) | DASH-001 | done |
| [DASH-003](DASH-003.md) | Session-to-downstream-header DI seam | DASH-002 | done |
| [DASH-004](DASH-004.md) | Run detail view (`GET /runs/{id}`, `GET /runs/{id}/splits`) | DASH-003 | done |
| [DASH-006](DASH-006.md) | Submit-a-run form (`POST /runs`) | DASH-003, DASH-004 | done |
| [DASH-007](DASH-007.md) | Logout / session invalidation | DASH-002, DASH-003 | done |
| [DASH-008](DASH-008.md) | Health check endpoint | DASH-001 | done |
| [DASH-009](DASH-009.md) | Selenium E2E suite for the core PoC loop | DASH-002, DASH-004, DASH-006, DASH-005-GAP fallback | done |

`DASH-005` (runs list, Must) is **deliberately deferred out of this sprint** — blocked on
`DASH-005-GAP`, which requires new, not-yet-authored `VS-0NN` (validation-service) and `GW-016`
(gateway-api) backlog tickets outside this sprint's/role's authority to schedule. `GW-017` (Locust
load-test suite, gateway-api backlog) deliberately kept out of this sprint for goal-coherence reasons,
not a dependency conflict. See docs/sprints/sprint-11.md's scheduling decisions for full reasoning.

## Execution / parallelization plan (Sprint 11)

- **Round 0 (Tech Lead, direct)**: DASH-001 — pure scaffolding, done directly rather than delegated,
  same precedent as NFE-001/VS-001/LC-001/GW-001.
- **Round 1**: DASH-002 (login screen, depends on DASH-001) — this sprint's most security-sensitive
  ticket, given the same extra scrutiny this repo gave GW-006/GW-007 in Sprint 05.
- **Round 2**: DASH-003 (DI seam, depends on DASH-002) — every later route depends on this exact
  header shape and unauthenticated-rejection-before-route-logic behavior.
- **Round 3**: DASH-004 (run detail, depends on DASH-003) — run to completion before DASH-006 starts.
- **Round 4**: DASH-006 (submit-a-run, depends on DASH-003 **and** DASH-004's redirect target) — not
  run in parallel with DASH-004 despite both formally sharing only DASH-003 as a common ancestor, per
  sprint-11.md's own sequencing correction.
- **Round 5 (parallel)**: DASH-007 (logout, depends on DASH-002+DASH-003) and DASH-008 (health check,
  depends on DASH-001 only) — disjoint files (`auth.py` vs `main.py`), safe to run together.
- **Round 6**: DASH-009 (Selenium E2E suite, depends on DASH-002/004/006 + the disclosed
  `DASH-005-GAP` fallback) — run last, exercises functionality that must already exist.

**Sprint 11 outcome**: all 8 in-scope stories (DASH-001-004, DASH-006-009) done, executed in this
plan's own dependency-first order, each personally verified by the Tech Lead against the actual diff
and a real test run — not merely trusted from a dev agent's own report. `services/dashboard-web` now
exists as a real, tested, running FastAPI + Jinja2/HTMX service: a tenant logs in with a `gateway-api`
API key (`DASH-002`, given GW-006/GW-007-level scrutiny — raw key confirmed never rendered, logged, or
placed in a URL, only sent as `Authorization: Bearer <key>`), every downstream call shares one DI seam
(`DASH-003`), a run's status and per-split results render from `gateway-api`'s real contract
(`DASH-004`), a new run can be submitted through a form matching `POST /runs`'s real shape exactly with
no shortcut around the purge gap or naive baselines (`DASH-006`), plus logout (`DASH-007`) and a real
DB-connectivity-style health check against `gateway-api` (`DASH-008`). `DASH-009`'s Selenium E2E suite
(the first browser-level suite in this platform) exercises all three flows end-to-end against a real
subprocess `dashboard-web` instance and a stub `gateway-api` fixture — one real bug was found and fixed
during personal verification (a test-authoring gap, not an app defect: the invalid-payload test needed
to disable native HTML5 form validation via JS to actually reach the server's own validation path; see
`docs/tickets/DASH-009.md`'s Outcome for full detail). Full suite: **47 passed**, 0 failed (42 unit +
5 e2e). `DASH-005` (runs list) is deliberately deferred, not built and not faked — `services/
dashboard-web/README.md` states this explicitly, and `DASH-009`'s "view a completed run" flow uses the
disclosed `DASH-005-GAP` fallback (the run id from `DASH-006`'s own redirect) rather than any
client-side substitute, confirmed via `grep` across `src/app/routers/` showing no list route exists.
`GW-017` (Locust) stays out of this sprint per its own scheduling decision. **Follow-up for the Product
Owner, not this sprint**: author and approve `VS-0NN` (validation-service tenant-scoped `GET /runs`
list) and `GW-016` (matching gateway-api proxy route) so a future sprint can unblock `DASH-005`.

## Sprint 15

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [DASH-005-01](DASH-005-01.md) | Runs list view (`GET /runs`) | `DASH-005-GAP` (closed, Sprint 14: VS-022 + GW-016), DASH-003 | done |
| [DASH-009-02](DASH-009-02.md) | `DASH-009` flow-3 update: navigate via the real list page | DASH-005-01 (this sprint) | done |

See docs/sprints/sprint-15.md. Closes `DASH-005` (Must, deferred since Sprint 11), the last disclosed
`dashboard-web`-side gap from the original Sprint 11 PoC scope, now unblocked by Sprint 14's
`DASH-005-GAP` closure. Sequenced strictly: `DASH-005-01` first (builds the real `GET /runs` page
against the real `RunListResponse`/`RunSummaryResponse` envelope documented in
`services/gateway-api/README.md`'s Contract section — `RunSummaryResponse` imported from
`naive_first_common.contracts`, `RunListResponse` itself is a router/page-local envelope, not a shared
contract class), then `DASH-009-02` (extends the already-`done` `DASH-009` Selenium suite's flow 3 to
navigate via the new list page instead of Sprint 11's disclosed redirect-id fallback — a same-story-ID
completion, not a new backlog item, per the sprint file's own explicit dissent-flagged reasoning).
`docs/tickets/DASH-009.md`'s Outcome section is appended, not overwritten, to record this update.

**Sprint 15 outcome**: both in-scope tickets done, executed in the sprint's own strict sequencing
order (`DASH-005-01` first, `DASH-009-02` second, run only after `DASH-005-01`'s diff was personally
verified), each personally re-verified by the Tech Lead against the actual diff and a real test run —
not merely trusted from either dev agent's own report. **`DASH-005-01`**: `GET /runs`
(`src/app/routers/runs.py`) added, reusing `DownstreamHeadersDep`/`GatewayApiUrlDep`/`_call_downstream`
unchanged, `RunSummaryResponse` imported from `naive_first_common.contracts` (confirmed not
redefined), `RunListResponse` confirmed **not** imported from there (it doesn't exist in that module —
correctly treated as a page-local envelope per gateway-api's own README convention). A new
`_render_error_for_status` helper was extracted, replacing what would otherwise have been a fourth
near-identical `502`/`504` branch (past the "extract on second duplication" threshold,
implementation-plan.md section 9). `grep` across `src/app/` confirmed no client-side
persistence/caching/index of runs anywhere. `uv run pytest -q`: **50 passed**, 5 deselected (42
pre-existing + 8 new, zero regressions). `services/dashboard-web/README.md`'s status line/Known-gaps
note and `docs/product/backlog-dashboard-web.md`'s `DASH-005` entry (now `[Must, done]`, all
acceptance-criteria boxes checked) both confirmed updated. **`DASH-009-02`**: flow 3's navigation in
`tests/e2e/test_core_loop.py` now goes through the real `GET /runs` list page and a click on the
run's own `a[href='/runs/{run_id}']` link, rather than driving straight to the post-submit redirect
URL; `tests/e2e/stub_gateway_api.py` gained a matching `GET /runs` handler (real envelope shape,
sourced from the stub's own `_runs` dict, reusing existing helpers) so the fixture gateway-api
supports the real list page's downstream call. `git status` scoped to `src/app/routers/` and
`src/app/templates/` confirmed zero changes from this ticket. `uv run pytest -q`: **50 passed**, 5
deselected (unchanged); `uv run pytest -m e2e -q`: **5 passed**, 0 failed (unchanged count, same 5
flows, one flow's navigation mechanism changed). **Non-tautological regression proof, personally
performed by the Tech Lead**: temporarily removed the `<a href="/runs/{{ run.id }}">` link from
`runs_list.html`, re-ran `test_submit_run_valid_payload_redirects_and_shows_completed_results` alone —
it failed (`TimeoutException` waiting for the link), confirming the test genuinely exercises
`DASH-005-01`'s list page rather than passing regardless of whether it works; the template was then
reverted (diffed byte-identical against the pre-change version) and the test re-confirmed passing.
**Combined final count for `services/dashboard-web`: 55 tests (50 unit + 5 e2e), 0 failed.**
**`DASH-009` scope-decision note**: the Tech Lead proceeded with `DASH-009-02` in this sprint (rather
than pulling it out per the sprint file's own dissent flag) because the change was bounded (touched
only `tests/e2e/`, zero `src/app/routers/`/`templates/` changes, confirmed both by grep and by
`git status`), was twice already flagged as expected future work in Sprint 11's and Sprint 14's own
handoff notes, and added no new externally-visible `dashboard-web` capability — it closed out
`DASH-009`'s own already-approved acceptance criteria against its originally-preferred dependency
once that dependency (`DASH-005`) came to exist, rather than introducing new product scope.

# services/reporting-service (RS-*)

Source: docs/product/backlog-reporting-service.md, docs/sprints/sprint-12.md. Sprint goal: a `"validation_audit"` HTML
report can be generated for a validation-service run, either synchronously via a manual endpoint or
automatically on that run's `run.completed` Redis Streams event, and retrieved afterward through a
tenant-isolated endpoint. Deliberate, disclosed override of trigger #7 (implementation-plan.md
section 6) -- no pilot audit request exists yet, same disclosed-override precedent as `gateway-api`
(trigger #5) and `dashboard-web` (trigger #8).

## Sprint 12

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [RS-001](RS-001.md) | Service scaffolding | none | done |
| [RS-002](RS-002.md) | `reporting` Postgres schema + Repository pattern with RLS | RS-001 | done |
| [RS-003](RS-003.md) | Report Factory + "validation audit" renderer | RS-001 | done |
| [RS-004](RS-004.md) | Manual `POST /reports/generate` endpoint | RS-002, RS-003 | done |
| [RS-005](RS-005.md) | `GET /reports/{id}` retrieval endpoint | RS-002 | done |
| [RS-006](RS-006.md) | Redis Streams subscriber for `run.completed` | RS-002, RS-003, RS-004 | done |
| [RS-007](RS-007.md) | Health check endpoint | RS-002 | done |
| [RS-008](RS-008.md) | OpenAPI contract / README doc-sync check | RS-004, RS-005 | done |
| [RS-009](RS-009.md) | CI wiring | RS-001 through RS-006 | done |

## Execution / parallelization plan (Sprint 12)

- **Round 0 (Tech Lead, direct)**: RS-001 -- pure scaffolding, done directly rather than delegated,
  same precedent as NFE-001/VS-001/LC-001/GW-001/DASH-001.
- **Round 1 (parallel)**: RS-002 (`repositories/`+`models.py`+`migrations/`, security-sensitive --
  RLS cross-tenant proof must run as a real non-superuser role) and RS-003 (`renderers/`+
  `templates/`, positioning-sensitive -- DM verdicts pass through verbatim, disclaimer mandatory) --
  disjoint files, both depend on RS-001 only.
- **Round 2**: RS-004 (manual generate endpoint, depends on RS-002 AND RS-003 both actually done) --
  its own `src/app/generation.py` extracts the fetch-render-persist sequence into a reusable function
  RS-006 must later import, not duplicate.
- **Round 3 (parallel)**: RS-005 (`GET /reports/{id}`, depends on RS-002 only, deliberately its own
  router file `report_retrieval.py` disjoint from RS-004's `report_generation.py` to avoid file
  overlap, mirroring VS-007/VS-008's `runs.py`/`splits.py` split) -- run in parallel with nothing
  else at this point since RS-004 must land first for RS-006's own dependency; RS-005 itself could
  have run alongside RS-004 in Round 2 (file-disjoint), scheduled in its own round here for clarity.
- **Round 4**: RS-006 (Redis subscriber, depends on RS-002, RS-003, RS-004 -- specifically reuses
  RS-004's `generate_validation_audit_report` function, flagged for review scrutiny if a duplicate
  sequence appears).
- **Round 5 (Should, tail work)**: RS-007 (health check, depends on RS-002), RS-008 (doc-sync check,
  depends on RS-004+RS-005), RS-009 (CI wiring, depends on RS-001 through RS-006, runs last).

**Sprint 12 outcome**: all 9 in-scope stories (RS-001 through RS-009) done. `services/reporting-service`
now exists as a real, tested FastAPI service: `reporting.reports` Postgres schema behind a
`ReportRepository` with real RLS enforced against the non-superuser `naive_first_app` role (RS-002);
a Factory + `ValidationAuditRenderer` reproducing the `naive-first-audit` skill's report structure
with DM verdicts passed through verbatim and the mandatory disclaimer present in every report,
including status-only ones (RS-003); `POST /reports/generate` (RS-004) and `GET /reports/{id}`
(RS-005), both tenant-isolated via `naive_first_common.get_tenant_context`; a Redis Streams
subscriber on `run.completed` (RS-006) that reuses RS-004's own `generate_validation_audit_report`
function with zero duplicated fetch/render/persist logic and a real defense-in-depth status re-check
against the freshly fetched run detail, not the event payload; a real-DB `GET /health` (RS-007); a
route-existence doc-sync check (RS-008); and CI wiring matching every other module's pattern exactly
(RS-009). Final full-suite count, independently re-confirmed by the Tech Lead multiple times from
fresh copies outside the OneDrive-synced tree (not taken on any single dev agent's report alone):
**36 passed, 0 failed**, including the real-Postgres RLS cross-tenant proof
(`test_rls_blocks_cross_tenant_reads_at_the_database_level`, run as the actual non-superuser
`naive_first_app` role) and the real-Redis integration tests in `test_subscriber.py` (not
skip-guarded away -- both Postgres and Redis were reachable throughout this sprint's execution).
Two dev-agent sessions (RS-002, RS-006's first attempt) were interrupted by usage limits before
updating their own ticket files; in both cases the Tech Lead found the shipped code and tests already
complete and correct on disk, personally verified them (including, for RS-002, discovering and fixing
a real environment gap -- the `reporting` schema had never been migrated onto the live Postgres
container -- and diagnosing a severe Postgres-connection slowdown down to the same IPv6-loopback
`localhost` DNS quirk this repo's own Sprint 09 already documented, worked around via
`PGCONNECT_TIMEOUT`), and completed the ticket files/README documentation acceptance criteria
directly rather than re-delegating from scratch. RS-006's second attempt (after the first was
declared dead) succeeded cleanly on its own. Every ticket's Review acceptance criteria were personally
verified by the Tech Lead reading the actual diff/files and independently re-running tests -- not
trusted from any dev agent's self-report alone, per this sprint's own extra-scrutiny flags on RS-002
(RLS proof against a real non-superuser role) and RS-003 (DM-verdict verbatim passthrough, disclaimer
presence, no positioning violations).

**Known gap, disclosed not silently accepted**: `docs/sprints/sprint-12.md`'s own on-disk content was
found to be genuinely mismatched with this sprint at the start of this work (containing
`services/economic-service` planning content instead of `services/reporting-service`, despite its own
commit message correctly reading "Sequence Sprint 12: services/reporting-service PoC") -- this sprint
was executed from the requester's own detailed restated framing, cross-verified directly against
`docs/product/backlog-reporting-service.md` (which matched that framing exactly), not from the
mismatched file. The coordinator has since confirmed this was a concurrent-session write race and
restored the file's correct content separately -- not an action taken by this sprint's own tickets.
`RS-GAP` (no `gateway-api` proxy route for this service's endpoints, not yet wired into
`infra/docker-compose.yml`) remains open by design, per the backlog's own explicit scope decision --
follow-up `GW-0NN`/`INF-0NN` tickets are needed before this service is reachable end-to-end through
the platform's one public-facing surface.

# services/economic-service (ECON-*)

Source: `docs/sprints/sprint-13.md`, `docs/product/backlog-economic-service.md`. **This is not a routine trigger override.** Trigger #11 (implementation-plan.md section 6) exists "per the ethical boundary in docs section 2.7" — CLAUDE.md's own binding rule: "only wire up for a model that already beats naive in `validation-service`; never claim profitability before that." That trigger has **not** fired: no model has ever beaten Naive0 on this platform, and `VS-017` (the precondition for a real client-model DM verdict to even exist) is itself deferred and unbuilt in `validation-service`. Sprint 13 is a disclosed, user-authorized override building **scaffolding only** — an inputs-only Postgres schema, typed contracts, a mock-only upstream integration, and a structural, code-enforced eligibility gate (`ECON-005`) that makes it provably impossible for the shipped service to return a real profitability number today, not just documented as forbidden.

## Sprint 13

| Ticket | Story | Depends on | Status |
|---|---|---|---|
| [ECON-001](ECON-001.md) | Service scaffolding | none | done |
| [ECON-002](ECON-002.md) | `economic.*` Postgres schema + Repository pattern for cost/slippage *inputs* (never a profitability-output table) | ECON-001 | done |
| [ECON-003](ECON-003.md) | Contracts: `SimulationRequest` + two structurally disjoint response models (`EligibleSimulationResult`, `NotEligibleForSimulation`) | ECON-001 | done |
| [ECON-004](ECON-004.md) | Mocked-upstream-only integration (`MockValidationResultClient`, hard architectural rule, never a real `httpx` call) | ECON-001, ECON-003 | done |
| [ECON-005](ECON-005.md) | The structural eligibility gate (`POST /simulations`, `check_economic_eligibility`) — this sprint's actual deliverable | ECON-002, ECON-003, ECON-004 | done |
| [ECON-006](ECON-006.md) | No profitability language outside the gated computation path (README rewrite, grep-style doc-sync check, OpenAPI eligibility-precondition text) | ECON-001, ECON-005 | done |

## Execution / parallelization plan (Sprint 13)

- **Round 0 (Tech Lead, direct)**: ECON-001 — pure scaffolding, done directly rather than delegated, same precedent as NFE-001/VS-001/LC-001/GW-001/DASH-001/RS-001.
- **Round 1 (parallel)**: ECON-002 (`economic.*` schema/repositories, security- and ethics-sensitive — the inputs-only design decision) and ECON-003 (contracts, load-bearing for ECON-005's disjoint-response-shape requirement) — disjoint files, both depend on ECON-001 only, per sprint-13.md's own sequencing decision.
- **Round 2**: ECON-004 (mock-only upstream client, depends on ECON-001 and ECON-003 — needs `UpstreamValidationResult`'s exact shape to mock against; sequenced after both Round 1 branches land for simplicity, though it only strictly needs ECON-003).
- **Round 3**: ECON-005 (the structural eligibility gate, depends on ECON-002, ECON-003, ECON-004 — the first story needing all three prior branches complete). Given this repo's "extra scrutiny" treatment (same category as GW-006/GW-007, DASH-002), plus additional scrutiny beyond those per sprint-13.md's own instruction, since a mistake here is a business-honesty failure, not a bug.
- **Round 4**: ECON-006 (doc-sync/positioning polish, depends on ECON-001 and ECON-005 — its grep check needs ECON-005's guard/route code to exist to scan). Runs last.

**Sprint 13 outcome**: all 6 in-scope Must stories done. `.venv\Scripts\python.exe -m pytest -q` in `services/economic-service` passes **50/50**, 0 failed (2 ECON-001 smoke tests, 8 ECON-002 model/repository/no-profitability-column tests, 8 ECON-003 contract tests, 6 ECON-004 upstream-client tests, 5 ECON-005 eligibility-gate tests including all four required negative/positive-control tests plus the guard structural check, and ECON-006's doc-sync-check test suite — final count independently re-confirmed by the Tech Lead multiple times throughout the sprint, not taken on any single dev agent's report alone). Every ticket's Review acceptance criteria were personally verified by the Tech Lead reading the actual diff/files, not merely trusting a green checkmark — ECON-002's no-profitability-column-name regression guard and RLS authoring were read directly; ECON-004 was found by the Tech Lead to have two real test-authoring bugs (a false-positive AST-based "only implementer" check counting the Protocol interface's own stub method, and a false-positive raw-substring `_URL` check matching the module's own docstring prose) after its dev agent was interrupted by a session usage limit before self-verifying — both fixed by the Tech Lead directly and re-confirmed against a fresh grep of the real `src/app/` tree; ECON-005 (this sprint's highest-stakes ticket) received the sprint's mandated extra scrutiny — the Tech Lead personally re-ran all four required tests individually plus the guard structural check (all pass), read every route handler in `src/app/routers/` directly (only `create_simulation` exists; it never calls `compute_economic_simulation` directly), read `dependencies/upstream.py` directly (unconditional, branch-free `MockValidationResultClient` return) and grepped the whole `src/app/` tree for `httpx`/`"live"`/`os.environ`/`_URL` (zero real hits outside docstring prose and the guard's own comparison), and re-read `models.py`/the 0001 migration directly (three tables, zero profitability-output-shaped column names); ECON-006's drift-detection demonstration was personally reproduced end-to-end by the Tech Lead (inject a real violation → confirm the check fails with exit 1 and the exact expected hits → revert via a pre-injection backup → confirm `git diff` shows zero residual change → confirm the check and full suite pass clean again). Zero changes to any file under `libs/naive_first_engine`, `libs/common`, `services/validation-service`, `services/gateway-api`, `services/ingestion-service`, `services/reporting-service`, or `services/dashboard-web` — confirmed via `git status` scoped to those paths both before and after this sprint (a concurrent, unrelated `services/reporting-service` (RS-*) session was independently active on this same repo during this sprint; confirmed no cross-contamination into `services/economic-service`'s files by direct inspection). See `docs/sprints/sprint-13.md`'s own Outcome section for the full four-part non-negotiable verification writeup.

