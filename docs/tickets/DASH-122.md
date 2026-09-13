# DASH-122 — `GET /runs` client-side callers silently truncated to the first 20 runs (dashboard-web)

**Module**: `services/dashboard-web`. **Depends on**: none — same-pass production bug fix, per the
DASH-119/DASH-120/DASH-121 precedent (fix immediately rather than only file the ticket).

## Analysis

DBA agent performance review found a real correctness bug: `GET /runs` (proxied through
gateway-api's `GW-016`, itself proxying validation-service's `GET /runs`, `VS-022`) defaults to
`limit=20` when no `limit` query param is passed. Two `dashboard-web` features call it with **no**
explicit `limit`, silently getting only the 20 most recent runs even though both are supposed to
consider the tenant's full run history:

- `runs_horizon_summary` (`services/dashboard-web/src/app/routers/runs.py`, `FHS-002`) — filters
  the fetched runs client-side by `horizon`/`status == "completed"`. If a tenant has more than 20
  runs and the matching ones aren't in the most recent 20, they silently never appear.
- `runs_trend` (`services/dashboard-web/src/app/routers/runs.py`, `RAV-009`) — groups the fetched
  runs client-side by `(dataset_id, horizon)`. Same silent-truncation risk for the trend view and
  its consistency indicator (`RAV-010`).

Checked `services/validation-service/src/app/routers/runs.py`'s `list_runs` handler (`VS-022`)
before deciding the fix shape: `limit: int = Query(default=20, ge=1, le=100)` — a hard server-side
ceiling of 100, enforced with a real `422` above it, never silently clamped. That rules out "just
pass a large `limit`" as a genuinely sufficient one-shot fix: a single request at the maximum
allowed value (100) still silently truncates a tenant with more than 100 runs, just at a different
number than 20. `services/gateway-api`'s `GW-016` proxy forwards `limit`/`offset` unmodified — it
imposes no ceiling of its own beyond re-forwarding validation-service's `422`.

CLAUDE.md/implementation-plan.md constraint: no service reads another service's schema — this
ticket does not touch that boundary, it is a pure client-side call-parameterization bug inside
`dashboard-web`'s own router layer, fixed entirely with the existing `GET /runs`
`limit`/`offset` contract.

## Design

**Pattern**: none of implementation-plan.md section 7's listed patterns are newly introduced — this
is a call-site correctness fix, not a new architectural seam.

**Files touched** (scoped to `services/dashboard-web` only):
- `services/dashboard-web/src/app/routers/runs.py` — new `_fetch_all_runs(client, headers)` helper
  (module-level, alongside `_call_downstream`/`_fetch_ingestion_datasets`) that pages through
  `GET /runs` with `limit=100`/increasing `offset` until the response envelope's own `total` is
  satisfied or a short page is returned, then returns the concatenated `RunSummaryResponse` list.
  `runs_horizon_summary` and `runs_trend` are edited to call this helper instead of their existing
  bare `client.get(client.get, "/runs", headers=headers)` (no `limit`/`offset`).
- `services/dashboard-web/tests/test_runs_horizon_summary.py`,
  `services/dashboard-web/tests/test_runs_trend.py` — regression tests.
- `services/dashboard-web/README.md` — fix note.

**DRY check note** (grepped `client.get, "/runs"` and `_call_downstream(client.get, "/runs"` across
`services/dashboard-web/src/app/routers/runs.py` before writing this ticket): three existing bare
`GET /runs` call sites (`runs_list`, `runs_horizon_summary`, `runs_trend`). `runs_list`
(`DASH-005-01`) is deliberately excluded — it forwards a caller-supplied `limit`/`offset`
unmodified by its own existing design (its own docstring), which is correct behavior for a
paginated list-view route, not this bug's territory. Only the two client-side
filter/group-then-render call sites (`runs_horizon_summary`, `runs_trend`) are in scope. The new
`_fetch_all_runs` helper is written once and reused by both, rather than duplicating the
paging loop in each handler (implementation-plan.md section 9's "extract on second duplication"
rule, applied proactively here since both call sites need the identical loop from the outset).

## Implementation acceptance criteria

- [x] `_fetch_all_runs` pages through `GET /runs` via the existing `limit`/`offset` query params
      (no new backend endpoint) until the full run list is fetched, using the response envelope's
      own `total` field to know when to stop, and returns early with the failure signal on the
      first transport failure or non-200 response (mirroring `_call_downstream`'s own return
      shape, so callers reuse the existing `_render_error_for_status` branch).
- [x] `runs_horizon_summary` and `runs_trend` both call `_fetch_all_runs` instead of a bare,
      unparameterized `GET /runs` call.
- [x] `runs_list` (`DASH-005-01`) is unchanged — its own caller-supplied `limit`/`offset`
      forwarding behavior is untouched.

## Test acceptance criteria

- [x] A fixture with 25+ runs proves both features now see runs beyond the 20 most recent (e.g.
      the 21st-25th run, all within a single 100-item page — proves the simple over-20 case).
- [x] A fixture with 150+ runs proves real pagination across validation-service's hard `le=100`
      ceiling — a run only reachable via a second `offset=100` page is confirmed present in the
      rendered output for both `runs_horizon_summary` and `runs_trend`.
- [x] `uv run pytest -m "not e2e" -q` (`.venv\Scripts\python.exe -m pytest -q`) in
      `services/dashboard-web` run in full, zero regressions vs. the pre-fix baseline count.

## Review acceptance criteria (Tech Lead verifies personally)

- [x] Read the diff directly: `_fetch_all_runs` is a real paging loop against `limit`/`offset` (not
      a single larger `limit=` literal), and both `runs_horizon_summary`/`runs_trend` call it.
- [x] Confirm `runs_list` (`DASH-005-01`)'s existing caller-supplied `limit`/`offset` forwarding
      behavior is byte-for-byte unchanged.
- [x] Full test suite re-run directly by the Tech Lead (not merely trusted from a self-report).
- [x] Independent QA re-verification (`qa` subagent) that `FHS-002`/`RAV-009`/`RAV-010`'s existing
      behavior for tenants with fewer than 20 runs is unaffected (no new empty states, no changed
      ordering, no double-counting). **Done — verdict GO.** QA independently confirmed the loop is
      a genuine paging loop (not a bigger single `limit=`), confirmed `runs_list`'s own behavior is
      byte-for-byte unchanged, confirmed all four new tests are non-tautological, confirmed no
      existing FHS-002/RAV-009/RAV-010 assertion was altered, and re-ran the full suite (257
      passed, 7 deselected, 0 failed on a clean run). QA disclosed two non-blocking gaps: an
      unrelated `test_setup_wizard.py` order-dependent flake (out of this ticket's scope, should be
      filed separately) and no live-Compose-stack reproduction (accepted as unnecessary for a pure
      client-side pagination bug already covered by mocked-transport tests).

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md` gains a short fix-log section documenting the bug, why a
      single larger `limit` was insufficient (the server-side `le=100` ceiling), and the pagination
      fix, matching the DASH-119/120/121 precedent's format.

## Outcome

Fixed same-pass. `_fetch_all_runs` added to `services/dashboard-web/src/app/routers/runs.py`;
`runs_horizon_summary`/`runs_trend` both updated to use it. Four new regression tests added
(two per route: a 25-run single-page case, a 150-run two-page case). Full suite:
`.venv\Scripts\python.exe -m pytest -q -m "not e2e"` — **257 passed**, 7 deselected (e2e), 0
failed (253 baseline + 4 new). One unrelated, pre-existing failure
(`test_run_new_submit_invalid_horizon_shows_human_readable_error`, from concurrent in-flight
Sprint 32 work on `test_runs_submit.py`, not touched by this ticket) was investigated and confirmed
out of this ticket's scope — it did not reproduce on the final full-suite run.
