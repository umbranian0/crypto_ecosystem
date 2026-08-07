# Ticket index

Four modules are tracked here, kept as clearly separated sections: `libs/naive_first_engine` (NFE-*, Sprint 01+02, done), `services/validation-service` (VS-*, Sprint 03+04, done), `libs/common` (LC-*, Sprint 04, done for its in-scope Musts), and `services/gateway-api` (GW-*, Sprint 05, in progress).

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

**Sprint 05 outcome**: all 9 in-scope Must stories done. `.venv\Scripts\python.exe -m pytest -q` in `services/gateway-api` passes 55/55 (0 failures), including GW-004's revoked-key-still-resolves test, GW-006's full valid/missing/malformed/unknown/revoked auth coverage, GW-007's spoofed-inbound-header proof, GW-008's cross-tenant `404` tests, and GW-009's timeout/connection-refused/status:"failed"-pass-through tests. Zero regressions confirmed by re-running both other suites after the sprint: `services/validation-service` 51/51, `libs/common` 14/14 (both unchanged from Sprint 04's baseline). GW-001 was scaffolded directly by the Tech Lead (no design decision to delegate, same precedent as NFE-001/VS-001/LC-001); GW-002 through GW-009 were each delegated to a dev subagent and personally verified by the Tech Lead by reading the actual diff (not just trusting the agent's self-report) before being marked done. GW-006 (auth) and GW-007 (tenant forwarding) received the sprint's mandated extra scrutiny: GW-006 confirmed to hash exclusively with `hashlib.sha256`, compare only hash-to-hash (never plaintext), and never log/print the presented raw key anywhere; GW-007 confirmed via a direct `git status` scope check to touch zero files under `libs/common/` or `services/validation-service/`, and confirmed structurally (not just behaviorally) that `build_downstream_headers` cannot read the inbound request's own `X-Tenant-Id` header. No deviations from sprint-05.md's binding note: SHA-256 used throughout, never bcrypt/argon2/scrypt.

**Sprint 04 outcome**: all 4 in-scope `libs/common` Must stories (LC-001–004) plus VS-010 done, matching sprint-04.md's Definition of Done. `libs/common`: `.venv\Scripts\python.exe -m pytest -q` passes 14/14 (LC-002/003 unit tests + LC-004's standalone fail-closed app-level suite). `services/validation-service`: `.venv\Scripts\python.exe -m pytest -q` passes 51/51 (48 pre-existing Sprint 03 tests, now exercising `Depends(get_tenant_context)` instead of the interim field, plus 3 new VS-010 fail-closed-before-repository tests). Both READMEs updated (`libs/common` status "scaffolded"; `services/validation-service` Contract section documents the `X-Tenant-Id` header replacing the retired `tenant_id` body/query field). LC-001 was scaffolded directly by the Tech Lead (no design decision to delegate, same precedent as NFE-001/VS-001); LC-002/003/004/VS-010 were each delegated to a dev subagent and personally verified by the Tech Lead by reading the actual diff (not just trusting the agent's self-report) before being marked done — VS-010 in particular was checked for: `Depends(get_tenant_context)` imported unmodified from `naive_first_common` with no local reimplementation, the interim `tenant_id` field/params fully removed (not left dead), tenant-isolation logic unchanged apart from the source of `tenant_id`, and the new fail-closed test's non-tautological proof (a repository fake that fails the test if reached) run directly by the Tech Lead. No deviations from sprint-04.md's binding notes: 401 (not 400) used throughout LC-003/LC-004/VS-010; LC-001 never touched `services/validation-service/pyproject.toml`; VS-010 was the ticket that added `naive_first_common` to that file. No code outside `libs/common`/`services/validation-service` was touched.
