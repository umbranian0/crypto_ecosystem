# Ticket index — libs/naive_first_engine

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
