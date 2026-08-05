# Sprint 02 — libs/naive_first_engine (Should/Could hardening)

Sprint goal: extend confidence beyond the Sprint 01 hard gate — reproduce the thesis's 6h/24h tables (exercising the Harvey correction against real published numbers, not just synthetic unit tests), and add the two packaging/documentation safeguards the backlog flagged as follow-ups once the first lib shipped.

Backlog source: docs/product/backlog-naive-first-engine.md (2 Should + 1 Could story, deferred from Sprint 01)

Stories in scope (execution order):

1. **NFE-016** — Regression suite: reproduce the thesis's published 6h and 24h results tables. Depends on NFE-015 (done, Sprint 01). Exercises the Harvey-corrected DM path (NFE-012) against real published numbers for horizons > 1, which Sprint 01 only covered with synthetic unit tests.
2. **NFE-017** — Standalone publishability check. Depends on NFE-001 (done, Sprint 01). Confirms the library builds/imports with zero access to the rest of the monorepo, serving the licensing revenue line (da-tese-ao-produto.md section 2.4).
3. **NFE-018** — Public API doc-sync check. Depends on NFE-014 (done, Sprint 01). Confirms `libs/naive_first_engine/README.md`'s public function list doesn't drift from the actual code, per implementation-plan.md section 8.

These three stories touch disjoint files (new test files for NFE-016; a new standalone check script for NFE-017; a doc-sync script + README for NFE-018) and have no data dependency on each other — all three can run in parallel rather than sequentially, unlike Sprint 01's mostly-sequential chain.

Stories explicitly deferred: none remaining in the current backlog — this closes out `docs/product/backlog-naive-first-engine.md` in full (NFE-019/020 are Won't items, not stories, not scheduled).

Definition of done for this sprint:
- NFE-016's 6h/24h regression tests pass, with the same disclosure requirements as NFE-015 (synthetic/fixture-based reconstruction stated plainly, not buried) and explicit confirmation that the Harvey-corrected DM statistic differs from the uncorrected one on at least one fixture (proving the correction is actually exercised, not a no-op at these horizons).
- NFE-017's isolated-environment build/import check exists and is documented as re-runnable (e.g. a script under `libs/naive_first_engine/`), and is run once to confirm it currently passes.
- NFE-018's doc-sync check exists, is demonstrated to actually catch drift (per its own acceptance criteria — verified by intentionally breaking it once), and `README.md` stays accurate.
- `uv run pytest` (or the `.venv`-direct equivalent used throughout Sprint 01, per NFE-001's environment note) passes in `libs/naive_first_engine`, full suite, including the new NFE-016 tests.
- No code in this sprint touches any module outside `libs/naive_first_engine` — the backlog's scope boundary from Sprint 01 still applies.
- This sprint does not fire any new build trigger (trigger #3 already fired at the end of Sprint 01) — it hardens the already-triggered module rather than unblocking a new one.
