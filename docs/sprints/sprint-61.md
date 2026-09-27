# Sprint 61 — Epic D closure (RAV-016) + `validation.split_results` read-path hardening (DBOPT-011/012)

Sprint goal: by the end of this sprint, a realistic 550-split run's `run_detail` page loads in under 2 seconds
(one batched points call instead of up to 500 sequential ones), and `validation.split_results`'s own row-fetch
query (`get_splits`) is bounded and properly indexed end to end instead of always fetching, sorting, and
discarding every row of a run to render at most 500 of them.

Backlog source: `docs/product/backlog-run-analysis-visualization.md` (`RAV-016`, Epic D, added 2026-09-27) and
`docs/product/backlog-db-optimization.md` (`DBOPT-011`, Must, and `DBOPT-012`, Should, both "New Sprint 31").
This is a fix-and-finish sprint on the split-result/split-point **read path** — no new chart type, no new
visualization, no new user-facing feature surface. All three items are already approved, already prioritized;
this file sequences and wires them, it does not re-litigate whether to do them.

## Verification of the backlog's cited findings (done independently, not taken on trust)

- **`services/validation-service/src/app/routers/splits.py`, read in full**: confirms `get_splits` (line 162,
  `GET /runs/{run_id}/splits`, no `limit`/`offset` params, run-ownership 404 first), `get_splits_summary` (line
  180, `GET /runs/splits/summary`, RAV-012's already-shipped batched precedent — `run_id: list[str]` repeated
  query param, `RunSplitsSummaryResponse{items: list[RunSplitSummary]}`, `RunSplitSummary{run_id, splits}` reusing
  `SplitResultResponse` verbatim), and `get_split_points` (line 213, `GET /runs/{run_id}/splits/{split_index}/
  points`, VS-033, `limit`/`offset` default 20/0, `SplitPointsResponse{items, limit, offset, total}`) all exactly
  as the backlog describes. `_split_result_to_response` (line 127) is the one shared 20-field mapping both
  `get_splits` and `get_splits_summary` already reuse — the same DRY precedent RAV-016's new endpoint must follow
  for `SplitPointResponse`, not a second hand-mapping.
- **`services/validation-service/src/app/repositories/postgres_repository.py`, read in full**:
  `PostgresSplitResultRepository.get_splits` (line 189) — `SELECT ... WHERE run_id=:run_id AND tenant_id=:tenant_id
  ORDER BY split_index`, no `LIMIT`/`OFFSET`, confirming DBOPT-011 exactly. `get_splits_for_runs` (line 202) is
  RAV-012's already-shipped `.in_(run_ids)` batching precedent for **split_results** rows across runs.
  `PostgresSplitPointRepository.get_points` (line 233) — `SELECT ... WHERE run_id=:run_id AND tenant_id=:tenant_id
  AND split_index=:split_index AND created_at >= _retention_cutoff() ORDER BY timestamp`, one split at a time,
  confirming RAV-016's target exactly. No `get_points_for_splits`-equivalent batching method exists yet for
  `split_points` — this is genuinely new, additive repository surface, not a rename/repurpose of an existing
  method.
- **`services/gateway-api/src/app/routers/runs.py`, read in full**: `get_splits` (line 218, pure pass-through),
  `get_splits_summary` (line 230, RAV-012's pass-through of the batched summary endpoint — same 3-path-segment
  `/runs/splits/summary` route, deliberately chosen so its literal 3rd segment (`"summary"`) never collides with
  `/runs/{run_id}/splits`' literal 3rd segment (`"splits"`) regardless of route-registration order, confirmed in
  the router's own docstring), and `get_split_points` (line 254, pass-through of VS-033's single-split endpoint)
  all confirmed exactly as cited. This file is where RAV-016's new endpoint gets its gateway-api pass-through
  twin, following the exact same "mirror the envelope field-for-field, forward params unmodified, no business
  logic reimplemented" pattern already used by all three existing proxy handlers above.
- **`services/dashboard-web/src/app/routers/runs.py`, `run_detail` handler, read in full (lines 1263–1380)**:
  confirms the exact N+1 loop RAV-016 targets — one `client.get(f"/runs/{run_id}/splits/{split.split_index}/
  points", headers=headers)` call per split in `rendered_splits` (line 1330–1344), each call passing **no**
  `limit`/`offset` override, meaning each split's chart is built from at most the endpoint's own default of the
  first 20 persisted points in timestamp order (VS-033's `limit: int = Query(default=20, ...)`) — a pre-existing
  behavior, not something this sprint is asked to change. **Flagged, not fixed here** (out of this sprint's
  approved scope — RAV-016's own AC is a latency fix, not a "show more points per split" feature): RAV-016's new
  batched endpoint must preserve this same default-20-points-per-split behavior so this sprint doesn't silently
  change what's plotted, only how many round trips it costs to plot it. A per-split degrade-on-transport-failure
  contract already exists here (`build_predicted_vs_actual_chart([])` on a 502/504/transport error, line
  1336–1337) — RAV-016's batched call must preserve the same "one bad split degrades only that split's own chart,
  never the whole page" stance, now applied to the single batched call's own failure mode instead of per-split
  calls.
- **`services/validation-service/migrations/versions/0011_add_split_points_table.py`, read in full**: confirms
  `split_points` is a **plain table, not a hypertable** (`op.create_table`, no `create_hypertable` call), with RLS
  enabled/forced (`ENABLE ROW LEVEL SECURITY` / `FORCE ROW LEVEL SECURITY` / `tenant_isolation` policy, lines
  52–57) but **no index at all beyond its own primary key on `id`** — no `(tenant_id, run_id, split_index)`
  index exists today. **Flagged, real finding, out of this sprint's approved scope**: RAV-016's new batched query
  (`WHERE run_id=:run_id AND tenant_id=:tenant_id AND split_index IN (...) AND created_at >= cutoff`) will run as
  a sequential scan over the whole `split_points` table today — not chunk-scan pain like `DBOPT-003`'s hypertable
  finding (this table isn't partitioned), but a real, unindexed multi-column filter on a table that will only
  grow. **No `DBOPT-*` item covers `split_points` today** (it postdates the DB-optimization backlog's last pass —
  VS-031 shipped after DBOPT-001–012 were written). This is not this sprint's story to fix (not an approved
  backlog item, and I do not have authority to invent new DBA scope), but it should be routed back to the DBA
  for a `backlog-db-optimization.md` entry once this sprint's own batched endpoint gives that analysis a real
  query shape to `EXPLAIN` against — recommend the Tech Lead flag this to the requester/DBA explicitly at
  hand-off rather than silently absorbing an index migration into RAV-016's scope.
- **`services/validation-service/migrations/versions/0006_add_split_results_tenant_run_index.py`, read in full**:
  confirms the exact precedent DBOPT-012 extends — `CREATE INDEX ix_split_results_tenant_run ON
  validation.split_results (tenant_id, run_id)`, issued against the hypertable root, Postgres-only-guarded
  (no-ops under the SQLite test path), paired `downgrade()` dropping the same index. DBOPT-012's migration
  (next revision, `0013`, since `0012_add_runs_engine_fingerprint_columns.py` is the current head) follows this
  exact shape: `DROP INDEX ...; CREATE INDEX ix_split_results_tenant_run ON validation.split_results (tenant_id,
  run_id, split_index);` — same index name reused (a widen-in-place, not a new index alongside the old one),
  same root-table/auto-propagation mechanism, same Postgres-only guard.
- **`libs/common/src/naive_first_common/contracts.py`, read in full for the relevant shapes**: `SplitResultResponse`
  (line 295), `SplitPointResponse` (line 351, `timestamp`/`predicted`/`actual`/`baseline_key`), and `RunSplitSummary`
  (line 372, RAV-012's `{run_id, splits: list[SplitResultResponse]}`) all confirmed exactly as the backlog
  describes and as the "reuse verbatim, never a fourth hand-duplicated field list" convention (ARCH-003) requires
  RAV-016's new contract type to follow.
- **File-overlap check, done by reading every target file in full, not assumed from module names**:
  `services/validation-service/src/app/routers/splits.py` and `.../repositories/postgres_repository.py` are both
  touched by **RAV-016** (new batched points endpoint/repository method, operating on `split_points`/
  `SplitPointRepository`) and by **DBOPT-011** (new `limit`/`offset` handling on `get_splits`/
  `PostgresSplitResultRepository`, operating on `split_results`/`SplitResultRepository`) — same two files,
  disjoint classes/functions, different underlying table. `services/gateway-api/src/app/routers/runs.py` is
  touched by RAV-016 only (new pass-through) — DBOPT-011's `limit`/`offset` addition to the existing
  `get_splits` proxy is a smaller, additive change to an already-existing handler, not a new one, but still the
  same file. `services/dashboard-web/src/app/routers/runs.py`'s `run_detail` handler is touched by RAV-016 only
  (new batched call replacing the per-split loop) and, separately, by DBOPT-011 (updating its splits-fetch call
  to request a bounded page instead of the full list) — same file, same handler, two different call sites within
  it (the `GET /runs/{run_id}/splits` call vs. the per-split points loop) — see the sequencing/risk call below.
  A new migration file (`0013`, DBOPT-012) is untouched by either RAV-016 or DBOPT-011 — pure schema DDL, no
  application code.

## Decisions made here, not left open for the Tech Lead

### 1. RAV-016's batched points endpoint — exact route shape, decided

**Decision**: `GET /runs/{run_id}/splits/points`, accepting a repeated `split_index` query parameter (e.g.
`?split_index=1&split_index=2&...`), added to `services/validation-service/src/app/routers/splits.py` (same file
that already owns every `split_results`/`split_points`-adjacent read, per that router's own module docstring
precedent) and proxied pass-through by `services/gateway-api/src/app/routers/runs.py`.

- **Path shape, collision-checked**: `/runs/{run_id}/splits/points` is a 4-path-segment route
  (`runs`/`{run_id}`/`splits`/`points`), distinct in segment count from both `/runs/{run_id}/splits` (3 segments)
  and `/runs/{run_id}/splits/{split_index}/points` (5 segments) — no ambiguity with either existing route
  regardless of FastAPI route-registration order, the same reasoning `get_splits_summary`'s own docstring already
  applies to `/runs/splits/summary`'s non-collision with `/runs/{run_id}`.
- **Response shape**: a new canonical contract type in `naive_first_common.contracts`, `SplitPoints` —
  `{split_index: int, points: list[SplitPointResponse]}` — reusing `SplitPointResponse` verbatim (never a fourth
  hand-duplicated field list, ARCH-003), mirroring `RunSplitSummary`'s own `{run_id, splits: list[
  SplitResultResponse]}` shape one level down (per-split instead of per-run). The router's own local envelope
  (matching the established "local envelope, shared item shape" convention `SplitPointsResponse`/
  `RunSplitsSummaryResponse` already use): `RunSplitPointsResponse{items: list[SplitPoints]}`. Concretely: `{
  "items": [{"split_index": 1, "points": [...]}, {"split_index": 2, "points": [...]}]}` — a list keyed by
  `split_index` inside each item, not a raw JSON object with integer-valued keys (Pydantic/JSON object keys are
  always strings; a `list[SplitPoints]` avoids that friction entirely and matches `RunSplitSummary`'s existing
  precedent field-for-field instead of inventing a new envelope shape for this one endpoint).
- **Behavioral parity, explicit**: this endpoint's per-split point count defaults to the same 20-point limit
  `GET /runs/{run_id}/splits/{split_index}/points` already defaults to (VS-033) — this story does not change how
  many points are plotted per split, only how many round trips it costs to fetch them. Retention (VS-032) applies
  identically: a `split_index` whose points were pruned or never persisted degrades to an empty `points: []` for
  that entry, never an error and never a distinct treatment from the single-split endpoint's own empty-`items`
  behavior. Unlike RAV-012's `get_splits_summary` (which silently omits an unknown/cross-tenant `run_id` from a
  batch), this endpoint still needs `run_id`'s own ownership check first (run-ownership 404, matching `get_splits`/
  `get_split_points`'s existing stance) since a request is always scoped to exactly one run — but it must **not**
  additionally validate each requested `split_index` against `split_results` the way the single-split endpoint
  does (VS-033's "collapse into 404" rule): the `split_index` values passed in are always drawn from `run_detail`'s
  own already-fetched, already-validated `rendered_splits` list, so a per-index 404 would only ever fire on an
  internal bug, not a real user path, and firing it would fail the *entire* batch over one bad index — degrade
  that index's own entry to an empty `points: []` instead, consistent with the per-split degrade-on-failure
  contract `run_detail` already implements for transport failures.
- **The existing single-split `GET /runs/{run_id}/splits/{split_index}/points` endpoint (VS-033) is unchanged** —
  same contract, same behavior, stays live for the standalone `points-chart` route (RAV-015's own "kept, Tech
  Lead's call" decision, sprint-60).

### 2. DBOPT-011 vs. RAV-016 — confirmed distinct query/table paths, not to be conflated

**RAV-016 batches `split_points` reads** (per-timestamp predicted/actual triples, `SplitPointRepository.
get_points`'s table). **DBOPT-011 paginates the `split_results` row fetch itself** (per-split aggregated metrics,
`SplitResultRepository.get_splits`'s table) — a different query against a different table, even though both are
touched from the same two files (`splits.py`, `postgres_repository.py`) and both ultimately serve the same
`run_detail` page. Restated explicitly per the task's own instruction: **the Tech Lead must not conflate these
two tickets, and must not build one shared "pagination helper" spanning both tables** — `SplitResultRepository`
and `SplitPointRepository` remain separate repository classes with separate bounding logic; any shared bounding
utility (e.g. a `limit`/`offset`-clamping helper) belongs in a genuinely reusable module (or duplicated once, per
this repo's "extract on second duplication" DRY rule, implementation-plan.md section 9) — not force-fit into one
of the two repository classes on the other's behalf.

### 3. DBOPT-011's approach — decided, with an explicit UX-preservation constraint

**Decision**: add optional `limit`/`offset` query parameters to `get_splits`/`GET /runs/{run_id}/splits`, end to
end (validation-service → gateway-api pass-through), **defaulting to unbounded when omitted** — this preserves
the existing bare-`list[SplitResultResponse]` contract shape and existing behavior exactly for any caller that
doesn't pass them (zero contract break for a future SDK/API client, or any other current internal caller besides
`run_detail`/`runs_trend`). `run_detail` and `runs_trend` (the two identified over-fetching dashboard-web callers,
per DBOPT-011's own citation) are updated to request a server-side-bounded page — at most `MAX_RENDERED_SPLITS`
rows — instead of fetching the full unbounded list and truncating it in Python after the fact, which is the
literal waste DBOPT-011 names.

**Explicit constraint carried into the ticket, not left implicit**: `run_detail`'s existing behavior renders the
**most recent** `MAX_RENDERED_SPLITS` splits (`splits[-MAX_RENDERED_SPLITS:]`, list-order tail) and shows an
accurate "N of M splits shown" notice when truncated (`total_splits_count = len(splits)` today). DBOPT-011's
bounded fetch **must preserve both of these** — it must not silently flip from "most recent N" to "first N"
(a real, silent product regression for exactly the large-run case this ticket targets), and it must not silently
turn the truncation notice inaccurate or remove it. The Tech Lead's implementation choice for satisfying this
(e.g. a `count_splits` companion method mirroring `ValidationRunRepository`'s already-established `list_runs`/
`count_runs` pair, or a descending-order fetch reversed in application code, or another mechanism) is not
prescribed here — this is genuinely a "how," not a "what," and stays the Tech Lead's call — but the constraint
itself (preserve tail-selection semantics and notice accuracy) is a binding acceptance criterion for this
ticket, not an implementation detail that can be quietly dropped for simplicity.

### 4. DBOPT-011/DBOPT-012 sequencing — confirmed and restated

The backlog's own dependency note ("DBOPT-011 depends on DBOPT-012 for the DB side to actually pay off once
pagination is added") is confirmed accurate by the live `EXPLAIN` evidence in DBOPT-012's own writeup — it is a
performance dependency (DBOPT-011 works correctly without DBOPT-012, just with an avoidable `Sort` node once
pagination is bounded to `ORDER BY split_index` at scale), not a correctness dependency. **Execution order
decided: DBOPT-012 first, DBOPT-011 second.** Rationale: DBOPT-012 is a pure, isolated, additive schema migration
(no application code touched at all — confirmed by its migration-shape citation) with no risk of colliding with
anything else this sprint touches; landing it first means DBOPT-011's new bounded/limited query pattern is
written and tested against the already-widened `(tenant_id, run_id, split_index)` index from day one, instead of
shipping a working-but-sort-heavy pagination change now and having to re-verify it again once DBOPT-012 lands
later. This also gives QA one live `EXPLAIN` to re-run (index eliminates the `Sort` node) before DBOPT-011's own
row-count-bounding behavior is verified on top of it.

### 5. Overall sequencing and file-overlap resolution

**Order: DBOPT-012 → DBOPT-011 → RAV-016.** DBOPT-012 first per the rationale above (isolated, zero app-code
risk, unblocks DBOPT-011's payoff). DBOPT-011 second: it touches `splits.py`/`postgres_repository.py`'s
`split_results`-related functions plus `run_detail`/`runs_trend`'s own splits-fetch call sites in dashboard-web.
RAV-016 third, **not run in parallel with DBOPT-011 despite touching different underlying tables** — both edit
the same two validation-service files (`splits.py`, `postgres_repository.py`) and the same dashboard-web
`run_detail` handler, and per this platform's own sprint-60 precedent (RAV-011/012/013/014 sequenced serially
for the identical reason — same-file, same-handler concurrent-diff risk, not a data dependency in every case),
these two tickets should land as serial, non-overlapping-in-time edits, not parallel dev-track dispatches. This
is not a case for merging them into one ticket — the two touch genuinely disjoint functions/classes within those
shared files (RAV-016 adds new `SplitPointRepository`/`split_points`-endpoint surface; DBOPT-011 modifies existing
`SplitResultRepository.get_splits`/`GET /runs/{run_id}/splits` surface) — keeping them as two tickets, sequenced
back-to-back, mirrors exactly how sprint-60 handled its own same-file overlap without merging RAV-013/RAV-014 into
one ticket either.

## Stories in scope, in execution order

1. **DBOPT-012** — Widen `ix_split_results_tenant_run` to `(tenant_id, run_id, split_index)`.
   - Modules touched: `services/validation-service` only — one new migration file (`0013`, following
     `0006_add_split_results_tenant_run_index.py`'s exact `DROP INDEX; CREATE INDEX` shape, Postgres-only-guarded,
     issued against the hypertable root). No repository/router/model code touched.
   - No dependency on any other story this sprint. Sequenced first: smallest, most isolated, zero application-code
     risk, and DBOPT-011 pays off fully only once this lands (see sequencing decision above).
   - **Binding constraint, restated per the task's own instruction: do NOT relax `FORCE ROW LEVEL SECURITY`.**
     `split_results` carries it (`0002_add_row_level_security.py`), and `DBOPT-008`'s BLOCKED status (compression
     unconditionally fails against any RLS-enabled table, live-reproduced, escalated to the user, not resolved) is
     the standing precedent for why relaxing RLS is off the table without explicit escalation. This migration does
     not need to touch RLS at all — `DROP INDEX`/`CREATE INDEX` on a hypertable root is DDL, not a data-path RLS
     bypass; it runs under `FORCE ROW LEVEL SECURITY` exactly as `0006`'s original index creation already did
     against this same table. State this explicitly to the Tech Lead so it isn't second-guessed or escalated
     unnecessarily — this is not the same class of operation `DBOPT-008` got blocked on.
   - Test: `alembic upgrade head` (including this migration) still succeeds and no-ops cleanly against a `sqlite://`
     `DATABASE_URL` (matching `test_alembic_upgrade_head_creates_matching_schema`'s existing convention, per
     `0006`'s own citation of that test). `downgrade()` round-trips (drops the 3-column index, recreates the
     original 2-column one) cleanly.

2. **DBOPT-011** — Bound `get_splits`/`GET /runs/{run_id}/splits` with `limit`/`offset`, and update `run_detail`/
   `runs_trend` to request a bounded page.
   - Modules touched: `services/validation-service` (`routers/splits.py`'s `get_splits` handler gains optional
     `limit`/`offset` query params; `repositories/postgres_repository.py`'s `PostgresSplitResultRepository.
     get_splits` gains the corresponding SQL-level bound; the SQLite counterpart in `sqlite_repository.py` gets the
     same signature for parity, matching every other dual-backend repository method in this codebase),
     `services/gateway-api` (`routers/runs.py`'s existing `get_splits` proxy forwards the new optional params,
     unmodified pass-through), `services/dashboard-web` (`routers/runs.py`'s `run_detail` and `runs_trend` handlers
     updated to request a bounded page instead of the full list).
   - Depends on `DBOPT-012` for the bounded/ordered query to be index-served without a `Sort` node from day one
     (performance dependency, not a correctness one — see decision #4 above). Sequenced second.
   - Constraint carried into the ticket, restated from decision #3 above: unbounded-by-default when `limit`/
     `offset` are omitted (zero contract break); `run_detail`'s "most recent N, accurate N of M" behavior must be
     preserved exactly, not silently changed to "first N" or an inaccurate/dropped truncation notice.
   - File-overlap note: shares `splits.py`/`postgres_repository.py` with RAV-016 (see decision #5) — sequence
     serially, not in parallel; shares dashboard-web's `run_detail` handler with RAV-016 too (different call site
     within the same function — the `GET /runs/{run_id}/splits` call vs. the points-fetch loop RAV-016 replaces).
   - Test: `get_splits` returns the full unbounded list when no `limit`/`offset` given (regression check against
     today's behavior); returns a correctly bounded/ordered page when given; `run_detail`'s "N of M splits shown"
     notice is still accurate and still reflects the most-recent-N tail for a fixture run exceeding
     `MAX_RENDERED_SPLITS`.

3. **RAV-016** — Batch `run_detail`'s per-split points fetching into one call, with a stated <2s latency budget.
   - Modules touched: `services/validation-service` (new `GET /runs/{run_id}/splits/points` endpoint in
     `routers/splits.py`; new `SplitPointRepository.get_points_for_splits(tenant_id, run_id, split_indices) ->
     dict[int, list[SplitPointRecord]]`-shaped method in both `postgres_repository.py` — a `.in_(split_indices)`
     query mirroring `get_splits_for_runs`'s own `.in_(run_ids)` precedent exactly — and `sqlite_repository.py` for
     parity), `libs/common` (`naive_first_common.contracts` gains `SplitPoints`, per decision #1 above),
     `services/gateway-api` (`routers/runs.py` gains the pass-through proxy for the new endpoint), `services/
     dashboard-web` (`routers/runs.py`'s `run_detail` handler's per-split points loop, lines 1330–1344, replaced
     by one batched call).
   - Depends on `RAV-015` (fixes the call pattern it introduced) and reuses `RAV-012`'s proven batched-endpoint
     precedent (mechanism, not code) — both already shipped, no new dependency work needed this sprint. Sequenced
     last per decision #5 (file-overlap avoidance with DBOPT-011, not a data dependency on it — `split_points` and
     `split_results` are independent tables).
   - Constraint carried into the ticket: exact route/contract shape per decision #1 above (not open for
     re-negotiation — founder-decided mechanism, PM-decided shape); behavioral parity (same default 20-points-
     per-split, same retention/pruning degrade-to-empty behavior, same per-split-failure-degrades-only-that-chart
     stance now applied to the batched call's own failure mode); the existing single-split points endpoint (VS-033)
     stays unchanged for the standalone `points-chart` route.
   - **Stated latency budget, non-negotiable per the backlog's own AC**: a realistic 550-split run's `run_detail`
     page must complete server-side in under 2 seconds, down from ~20s measured in Sprint 60 QA. Not met by any
     implementation still issuing more than one downstream points call per page load, regardless of individual
     call latency.
   - **Flagged, out of scope, routed to the DBA backlog, not fixed in this ticket**: `split_points` has no index
     beyond its PK (`id`) — confirmed by direct read of `0011_add_split_points_table.py` above. This ticket's new
     `IN (...)`-filtered batched query will run as an unindexed scan over the whole table today. Not this sprint's
     scope to fix (no approved `DBOPT-*` item covers it), but the Tech Lead should flag this explicitly to the
     requester/DBA as a likely next `DBOPT-*` candidate once this ticket gives it a real, `EXPLAIN`-able query
     shape to evaluate against.
   - Test: a fixture of N rendered splits results in exactly one batched downstream call to the new points
     endpoint, not O(N) (mirroring RAV-012's own "provably bounded, not just asserted in a docstring" requirement).
     A fixture 550-split run's `run_detail` handler completes within the stated 2s budget in a repeatable,
     automated measurement, not a one-off manual timing.

## Module/dependency note for the Tech Lead (implementation-plan.md sections 2 and 6)

All three stories touch only already-live modules — `services/validation-service` (trigger #3), `services/
gateway-api` (trigger #5), `services/dashboard-web` (trigger #8), and `libs/common` (trigger #2, RAV-016's new
`SplitPoints` contract type) — all fired long ago, no trigger question. No new service, no new `libs/*` package,
no touch to `libs/sdk` (trigger #9), `naive_first_engine`, `services/economic-service` (trigger #11), or any
ingestion connector. Per section 2's module boundary rule: `dashboard-web` reaches both RAV-016's new batched
points data and DBOPT-011's bounded split-results page only through `gateway-api`'s HTTP API, never
`validation-service`'s schema directly; `gateway-api`'s two touched endpoints stay pass-through only, never a
reimplementation of `validation-service`'s own query/aggregation logic (CLAUDE.md's "no service imports another
service's code" rule). DBOPT-012 stays entirely inside `validation-service`'s own schema boundary, per
`backlog-db-optimization.md`'s own scope statement ("no item here requires another service's schema to change").

## Stories explicitly deferred

- No story from either source backlog is deferred out of this sprint's approved scope — `RAV-016`, `DBOPT-011`,
  and `DBOPT-012` are exactly the three items named in this sprint's brief, and no other open item from either
  backlog file was pulled in or left out by this plan.
- **ADMIN-005** (self-serve API key rotation, Epic C of `docs/product/backlog-trust-and-admin-ops.md`) — still
  deferred, not dropped, carried forward unchanged from sprint-59/60's own "Next" sections; the founder redirected
  scope to this read-path hardening work instead. Its lockout-guard design risk and the recommendation for a
  `/grilling` pass before implementation remain unaddressed by this sprint and are not re-litigated here.
- **`split_points` indexing** (flagged above, under RAV-016) — not deferred in the formal backlog sense (it isn't
  an approved backlog item at all yet), but explicitly named here as a real, DBA-backlog-shaped gap this sprint's
  own work will make newly visible and measurable, for the requester/DBA to pick up as a future `DBOPT-*` item.

## Definition of done for this sprint

- `DBOPT-012`, `DBOPT-011`, and `RAV-016`'s acceptance criteria (verbatim from their respective backlog files)
  are checked off in their respective tickets.
- Required tests, specifically (restated from each story's own section above): `DBOPT-012` — migration
  round-trips cleanly on both Postgres and the SQLite no-op path. `DBOPT-011` — unbounded-by-default regression
  test, correct bounded/ordered page when `limit`/`offset` given, `run_detail`'s "most recent N, accurate N of M"
  behavior preserved for a fixture run exceeding `MAX_RENDERED_SPLITS`. `RAV-016` — provably-bounded single-call
  test (not O(N)), automated 550-split latency-budget test (<2s), retention/pruning parity test, per-split-failure
  degrade-only-that-chart test for the batched call's own failure mode.
- Positioning check (CLAUDE.md), restated per this repo's standing Definition-of-Done convention even though this
  sprint is pure plumbing/perf work with no new copy or chart: no price-prediction or trading-signal framing is
  introduced anywhere (not expected here — no new label, chart, or user-facing copy is added by any of the three
  stories), naive-first stays the default benchmark wherever touched, no green/red color pairing introduced
  (none of these stories touch chart rendering/color logic at all — `build_predicted_vs_actual_chart` itself is
  unchanged, only its data-fetching path changes).
- `services/dashboard-web/README.md`, `services/gateway-api/README.md`, and `services/validation-service/README.md`
  updated to record: the new batched points endpoint and its route/contract shape (`RAV-016`), the new `limit`/
  `offset` params on `GET /runs/{run_id}/splits` and dashboard-web's updated bounded-fetch behavior (`DBOPT-011`),
  and the widened `(tenant_id, run_id, split_index)` index (`DBOPT-012`) — as shipped, per this repo's
  README-current standing convention.
- `libs/common/README.md` (or its contract-listing section) updated to record the new `SplitPoints` contract type
  `RAV-016` adds to `naive_first_common.contracts`.
- `docs/product/backlog-run-analysis-visualization.md`'s `RAV-016` entry marked done with its acceptance-criteria
  boxes checked, pointing to its ticket file. `docs/product/backlog-db-optimization.md`'s `DBOPT-011`/`DBOPT-012`
  entries' status lines updated in place (matching the "Status: Done (Sprint NN, ticket ...)" convention every
  other closed `DBOPT-*` item in that file already uses) once shipped.
- `docs/tickets/README.md` gets a new Sprint 61 section (Tech Lead updates this when tickets are created/closed,
  per this repo's standing convention — not done by this sprint plan itself).
- The `split_points`-missing-index finding (flagged above) is explicitly carried into the Tech Lead's own
  close-out report to the requester, not silently absorbed into `RAV-016`'s ticket or silently dropped.
- **QA gate (mandatory, per this platform's standing rule): the Tech Lead raises the `qa` agent
  (`/qa-validation`) after all three tickets are Tech-Lead-verified done, before sign-off.** QA scope specifically,
  independently verified against the real `naive-first-*` Docker containers (not host-run scripts, which hit a
  stale local SQLite copy per this project's known topology gotcha, and not accepted from dev/Tech-Lead
  self-report alone):
  - **`run_detail`'s actual load time**, measured directly against a real many-split run (create or reuse a
    fixture run with at least 550 splits against the real stack) — confirm the <2s server-side budget is met with
    real measured numbers, not a fixture-test claim alone. If the real stack has no run of that size today, QA
    must state explicitly how it constructed or approximated one, not silently substitute a smaller run and claim
    the budget is met.
  - A live `EXPLAIN (ANALYZE, BUFFERS)` against the rebuilt stack confirming `DBOPT-012`'s widened index actually
    eliminates the `Sort` node on `get_splits`' `ORDER BY split_index` query — the same live-evidence standard
    `DBOPT-003`/`DBOPT-007`'s own QA passes already used.
  - `DBOPT-011`'s pagination actually bounds `get_splits`' returned row count for a large-split run, and
    `run_detail`'s truncation notice remains accurate (still reflects the true total, still shows the most recent
    N, not the first N) for that same fixture run.
  - `RAV-016`'s batched endpoint issues exactly one downstream points call per `run_detail` page load, confirmed by
    observing request counts/logs against the real stack for a many-split run — the same observation method
    sprint-60's own QA pass used for `RAV-012`.
  - No new label/copy was introduced by any of the three stories (expected — re-grep for prediction/forecast/
    signal/recommend language and any green/red color pairing in the touched files as a sanity check, consistent
    with this repo's standing QA checklist, even though none of these stories add new copy).

## Next (explicitly not this sprint, roadmap note)

With `RAV-016` shipped, `docs/product/backlog-run-analysis-visualization.md` has no remaining open story
(Epic D, and this backlog's entire scoped set, Epic A through D, complete). The next PM pass should: (1) confirm
with the requester/DBA whether the `split_points`-missing-index gap flagged under RAV-016 above should become a
new `DBOPT-*` backlog item, now that this sprint gives it a real, `EXPLAIN`-able query shape to evaluate; (2)
re-open `docs/sprints/sprint-59.md`'s "Next" section for `ADMIN-005` (self-serve API key rotation) as the standing
deferred candidate, still carrying its own flagged lockout-guard risk and the `/grilling`-before-implementation
recommendation — unless the requester redirects scope again; (3) evaluate the new DBA-shaped follow-up this
sprint's own QA pass surfaced (see the close-out below): `get_splits`' `ORDER BY split_index` `Sort` node is not
actually eliminated end-to-end by `DBOPT-012`'s widened index alone, because the query has no `test_start`
(chunk-partitioning-column) predicate for TimescaleDB's constraint exclusion to use — a real, `EXPLAIN`-backed
finding for a future `DBOPT-*` item, not fixed in this sprint.

## Tech Lead close-out (all three tickets done, QA gate cleared — GO)

All three tickets (`DBOPT-012`, `DBOPT-011`, `RAV-016`) were implemented by sequentially-dispatched `dev`
subagents (not parallel — per this file's own file-overlap sequencing call), personally reviewed by the Tech
Lead against their own Review acceptance criteria (every diff read in full against each ticket's Design section,
not taken on the dev agent's self-report), and re-verified against each touched module's own full test suite,
independently re-run by the Tech Lead after every ticket:

- `services/validation-service`: 238-261 passed across the sprint's several re-runs (row count grows as each
  ticket adds tests); one pre-existing, unrelated `created_at`/`list_runs`-ordering sqlite timing flake surfaced
  intermittently across runs (always passes standalone, confirmed pre-existing and untouched by this sprint's
  diffs — `list_runs`/its ordering logic is not modified by any of these three tickets).
- `services/gateway-api`: 249-252 passed / 1 pre-existing unrelated failure
  (`test_get_run_forwards_and_returns_full_detail_shape`, tracked since Sprint 60).
- `services/dashboard-web`: 455-457 passed / 8 deselected (Selenium e2e, excluded by default).
- `libs/common`: 48 passed (touched only by `RAV-016`'s new `SplitPoints` contract).
- Both machine-checked `check_doc_sync.py` scripts (`services/validation-service`, `libs/common`) pass.

**Files/migrations shipped**: `services/validation-service/migrations/versions/0013_widen_split_results_tenant_run_index.py`
(new); `services/validation-service/src/app/repositories/{interfaces,sqlite_repository,postgres_repository}.py`
(`get_splits` gains `limit`/`offset`, new `count_splits`, new `get_points_for_splits`);
`services/validation-service/src/app/routers/splits.py` (new `GET /runs/{run_id}/splits/count`, new
`GET /runs/{run_id}/splits/points`, `_split_result_to_response`/`_split_point_to_response` DRY extractions);
`libs/common/src/naive_first_common/contracts.py` (new `SplitPoints`); `services/gateway-api/src/app/routers/runs.py`
(pass-through proxies for both new routes, `limit`/`offset` forwarding on `get_splits`);
`services/dashboard-web/src/app/routers/runs.py` (new `_fetch_bounded_run_splits` helper used by `run_detail`/
`runs_trend`; `run_detail`'s per-split points loop replaced by one batched call). All four touched READMEs
(`validation-service`, `gateway-api`, `dashboard-web`, `libs/common`) updated as shipped, plus
`docs/product/backlog-run-analysis-visualization.md`'s `RAV-016` entry and `docs/product/backlog-db-optimization.md`'s
`DBOPT-011`/`DBOPT-012` entries, plus `docs/tickets/README.md`'s new Sprint 61 section.

**QA gate**: raised once, GO on first pass, no re-delegation needed. QA rebuilt and redeployed the real
`naive-first-dashboard-web`/`gateway-api`/`validation-service` Docker containers (found stale, ~27h old,
predating this sprint's code) before testing. QA independently constructed a real 550-split fixture run directly
in the real `naive-first-postgres` container (`run_id=812e16304b4346559c3eed42243e08eb`, a real existing tenant,
550 `split_results` rows landing almost entirely in the newer post-`0007` 90-day chunks, 11,000 `split_points`
rows, a scoped API key for session login) — fully disclosed in QA's report, and **cleaned up from the real stack
by the Tech Lead after QA's review concluded** (all fixture rows/API key deleted, verified zero remaining).
Measured results against that real fixture: `run_detail` loaded in 0.85-0.97s end-to-end (`curl -w
"%{time_total}"`, five clean runs) — well under the 2s budget and a ~20-23x improvement over Sprint 60's ~20s
baseline; exactly one batched `GET /runs/{run_id}/splits/points` call observed per page load across 10 observed
loads (zero occurrences of the old per-split pattern); `DBOPT-011`'s bounded fetch confirmed correct
(`?limit=3&offset=6` returns exactly that page; the real total is 550, `run_detail` accurately shows "the most
recent 500 of 550 splits," and the rendered table's actual split indices are 50-549, i.e. genuinely the tail, not
the first 500); the standalone single-split `GET /runs/{run_id}/splits/{split_index}/points` endpoint confirmed
unchanged and still live; no new prediction/forecast/signal/recommend language or green/red pairing found on the
real rendered page.

**One real, disclosed, non-blocking finding, not silently accepted**: QA's live `EXPLAIN (ANALYZE, BUFFERS)`
against the 550-split fixture (in the newer chunk regime, not the small/old-chunk case the implementing dev agent
had first flagged) found `DBOPT-012`'s widened index does **not** fully eliminate the `Sort` node on `get_splits`'
query end to end. Root cause: the query has no `test_start` (the hypertable's own partitioning column) predicate,
so TimescaleDB's constraint exclusion cannot prune any chunk regardless of index shape or run size — the query
always `Append`s every chunk, and Postgres's `MergeAppend` optimization (the only way to skip the `Sort`) requires
every child chunk scan to already be ordered, which fails the moment any low-row-count chunk gets a cost-based
`Seq Scan` instead of an `Index Scan`. The widened index does correctly serve the dominant chunk's own `Index
Scan` in order — it just cannot, alone, eliminate the outer `Sort` given the query's own shape. Absolute cost is
trivial (3.1ms execution on the fixture) and does not affect this sprint's Must-tier `RAV-016` latency budget,
which passed with a wide margin. **Corrected rather than left inaccurate**: `docs/tickets/DBOPT-012.md`'s Status
line and `docs/product/backlog-db-optimization.md`'s `DBOPT-012` entry were both rewritten to state this
precisely (index widened as designed, in-chunk ordering genuinely improved; full Sort elimination would need a
`test_start`-bound query or chunk consolidation, neither implemented here) rather than an unqualified "Sort
eliminated" claim — routed to the DBA/PM as a real follow-up candidate (see "Next" above), not silently absorbed
into this sprint's own scope.

**Deviation from the sprint plan's own text, disclosed**: the sprint plan named the mechanism for DBOPT-011's
"how" as the Tech Lead's own call among three named options (a `count_splits` companion method, a
descending-fetch-and-reverse, or another mechanism). The Tech Lead chose the `count_splits`-companion-method
option explicitly named as an example in the plan's own text — no deviation from anything the plan actually
decided, recorded here only because that "how" was genuinely left open and is worth stating plainly for future
reference.
