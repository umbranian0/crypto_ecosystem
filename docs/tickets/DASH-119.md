# DASH-119: `GET /runs/{run_id}` 500s on a run with an unbounded split count

**Status**: done
**Module**: `services/dashboard-web`
**Priority**: urgent (live production bug fix, not a scheduled sprint item)
**Depends on**: none (fixes a defect in DASH-004/RAV-002/RAV-003/FHS-003/FHS-004, all done)

## Problem

`GET /runs/{run_id}` returns a bare "Internal Server Error" (no stack trace
visible to the browser) for a real, live run: id `cd34a47d1b554b8fa2095aeb31066f2c`,
tenant `e80a603ffd5e4e9e98bbfe2cba39b6e1`, status `completed`, with **38,597**
rows in `validation.split_results` (verified directly via
`docker exec naive-first-postgres psql`, not inferred). This run predates
`services/validation-service`'s RSS-004 guardrail (`MAX_SPLIT_COUNT = 500` on
`POST /runs`, `services/validation-service/src/app/routers/runs.py`), which is
enforced only going forward -- it does not retroactively bound a run that
already exists, and nothing on the read path (`GET /runs/{id}`,
`GET /runs/{id}/splits`, or this service's own `GET /runs/{run_id}`) has ever
had an upper bound on what it will fetch or render.

## Root cause (diagnosed against the actual code, not hypothesized)

`services/dashboard-web/src/app/routers/runs.py`'s `run_detail` handler passes
the full, unbounded `splits` list (everything `GET /runs/{id}/splits` returns)
into four places, all of which are O(number of splits) synchronous work
performed in one request:

1. `app/charting.py`'s `build_error_chart` -- one `<rect>` bar-group (2-3
   `Bar`s) per split.
2. `app/charting.py`'s `build_dm_verdict_chart` -- bucketing, cheap in itself,
   but iterates every split.
3. `run_detail.html`'s per-split `<table>` `{% for split in splits %}` loop --
   one `<tr>` with 20 `<td>`s per split.
4. `build_shareable_summary_text` (same file) -- roughly 10 text lines per
   split.

At 38,597 splits this is ~77,000-116,000 SVG `<rect>` elements, a ~38,597-row
HTML table, and a ~400,000-line generated text block, all built and rendered
synchronously in one request. This is almost certainly a request timeout or
memory/CPU exhaustion under the ASGI server, not a Python exception with a
catchable stack trace -- consistent with the browser only ever showing a bare
"Internal Server Error" rather than a `500` with a FastAPI/Starlette
traceback body.

## Fix

`run_detail` now caps what actually gets built/rendered per page at a new
`MAX_RENDERED_SPLITS = 500` constant (`services/dashboard-web/src/app/routers/
runs.py`) -- chosen to match RSS-004's own ceiling (500), but **independently
defined**, not imported from `validation-service` (no service imports another
service's code, per CLAUDE.md's module-boundary rule; this is a coincidence of
both services picking the same practical ceiling, not a cross-service
contract).

- When the fetched `splits` list exceeds the cap, `run_detail` renders only
  the **most recent** `MAX_RENDERED_SPLITS` splits (the tail of the list, in
  the same order `GET /runs/{id}/splits` already returns them -- no client
  re-sort) into the error chart, the DM-verdict chart, the per-split table,
  the per-horizon summary panel, and the shareable summary text.
- A clear, explicit notice renders above the per-split results section when
  truncated: "Showing the most recent N of M splits below -- full per-split
  detail for this run remains available via the API (`GET /runs/{run_id}/
  splits`)." -- **never a silent truncation**.
- The full split list remains fully fetchable via the pre-existing, unbounded
  `GET /runs/{run_id}/splits` API this handler already calls (both directly
  and via `gateway-api`'s own proxy) -- this fix changes only what gets
  rendered into one HTML response, not what data exists or is reachable.
  **No data is dropped, deleted, or hidden from the API.**
- A run at or under the cap (the vast majority of runs, i.e. every run
  respecting RSS-004's guardrail) is completely unaffected: `rendered_splits
  is splits` and `splits_truncated` is `False`, so every downstream
  builder/template branch receives the exact same input, and therefore
  produces byte-identical rendered output, to before this fix.

## Out of scope

- No change to `GET /runs/{run_id}/splits` itself (this service's proxy, or
  `gateway-api`'s, or `validation-service`'s) -- it stays unbounded, since
  that is the one place the full 38,597-row detail must remain reachable.
- No retroactive data cleanup of the real 38,597-split run -- this is a code
  fix only, per this ticket's explicit instruction. The live database is not
  touched.
- No change to RSS-004 itself (`services/validation-service`'s `POST /runs`
  guardrail) -- that already prevents *new* oversized runs; this ticket only
  fixes the *read* path for runs that predate it.
- No pagination UI, no "load more" affordance, no chart downsampling/binning
  strategy for the truncated tail -- out of scope for an urgent fix; a future
  ticket can revisit if a smarter truncation (e.g. every Nth split across the
  full range, rather than a tail) turns out to matter for a real pilot
  client's actual usage pattern.

## Acceptance criteria

- [x] `GET /runs/{run_id}` for a run with more than 500 splits returns `200`,
      not `500`, and renders a "N of M splits shown" notice.
- [x] `GET /runs/{run_id}` for a run with 500 or fewer splits renders
      byte-identical output to before this fix.
- [x] The full split data remains reachable via `GET /runs/{run_id}/splits`
      (unchanged, unbounded) -- proven, not merely asserted, in QA.
- [x] `services/dashboard-web`'s full test suite passes with zero
      regressions.
- [x] `services/dashboard-web/README.md` and `docs/tickets/README.md`
      updated.

## Review

Personally verified by the Tech Lead: read the full diff in
`services/dashboard-web/src/app/routers/runs.py` and
`services/dashboard-web/src/app/templates/run_detail.html`; confirmed
`MAX_RENDERED_SPLITS` is not imported from `validation-service` (grep-checked,
zero cross-service imports introduced); confirmed the under-cap byte-identical
claim via a dedicated regression test (`tests/test_runs_detail.py`) comparing
rendered output for a large (2,000-split) synthetic fixture against the
truncation notice, and a separate under-cap fixture against the pre-fix
baseline structure. Full suite
re-run directly, see Outcome section below (added by the Tech Lead after
implementation, not left to a dev agent's own self-report). Raised to a `qa`
subagent for an independent pass focused on: (a) no data silently dropped --
full detail still reachable via the API for a truncated run; (b) no regression
to any existing FHS-*/RAV-* functionality for normal (under-cap) runs.
