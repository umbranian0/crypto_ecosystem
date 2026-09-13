# DASH-123 — QA-found (Sprint 31 UAT sweep): raw Pydantic error leak + silent out-of-range `days` (dashboard-web)

Urgent-fix ticket, same precedent as DASH-119/120/121/NFE-019: found fully-diagnosed by QA, fixed
minimally, no scope creep beyond the two diagnosed defects.

## Analysis

Two minor defects in `services/dashboard-web/src/app/routers/runs.py`, both found in the same QA UAT
sweep, both small fixes to the same file — one ticket per this session's own precedent for
same-sweep/same-file urgent fixes.

**Defect 1**: `run_new_submit`'s `except (ValueError, ValidationError) as exc` branch (client-side
`RunRequest(...)` construction, e.g. `horizon=0`) rendered `str(exc)` verbatim — Pydantic's raw
internal error text, including the `RunRequest` model class name and a `pydantic.dev` docs link,
inconsistent with this same route's other two hand-written error strings
(`_MISSING_DATASET_REFERENCE_ERROR`/`_INVALID_INLINE_JSON_ERROR`).

**Defect 2**: `runs_horizon_summary`'s `days: int | None = None` had no constraint against the
selector's actual supported set (`HORIZON_SUMMARY_DAY_OPTIONS = (7, 15, 30)`). An out-of-range value
(e.g. `days=999` or `days=-1`) rendered `200` with no active day-tab and an empty `runs` list —
indistinguishable from "no completed runs at a valid horizon."

## Design

No new design pattern — both are narrow, in-place fixes inside `runs.py`'s existing structure, not new
abstractions.

- Defect 1: new `_human_readable_run_request_error(exc)` helper, placed next to
  `_MISSING_DATASET_REFERENCE_ERROR`/`_INVALID_INLINE_JSON_ERROR`, mirroring their hand-written style
  — for a `ValidationError`, names the offending field(s) via `exc.errors()`; for a plain `ValueError`
  (e.g. non-integer input caught before `RunRequest` construction), a generic fallback message. Not a
  generalized error-formatting framework, per this ticket's own explicit "keep it simple" instruction.
- Defect 2: a single `if days not in HORIZON_SUMMARY_DAY_OPTIONS: raise HTTPException(422, ...)` guard
  added right after the existing `if days is None` early return, before the downstream `GET /runs`
  call — reuses the already-existing `HORIZON_SUMMARY_DAY_OPTIONS` constant, no new validation
  framework.
- File touched: `services/dashboard-web/src/app/routers/runs.py` only (single module).
- **DRY check note**: grepped `runs.py` for existing error-string constants and found
  `_MISSING_DATASET_REFERENCE_ERROR`/`_INVALID_INLINE_JSON_ERROR` — Defect 1's fix follows their exact
  style rather than inventing a new one. Grepped for existing 4xx-rejection patterns in this file and
  found none using `HTTPException` directly (existing 422s are all `TemplateResponse(..., status_code
  =422)` form-redisplays); `runs_horizon_summary` is a plain `GET` with no form to redisplay, so a bare
  `HTTPException(422)` is the simplest fit, not a manufactured redisplay.

## Implementation acceptance criteria

- `run_new_submit`'s `ValueError`/`ValidationError` branch no longer surfaces the `RunRequest` class
  name, `type=...` codes, or any `pydantic.dev` URL to the end user.
- `GET /runs/horizon-summary?days=<value not in (7, 15, 30)>` returns `422`, and does not call
  gateway-api.
- `GET /runs/horizon-summary?days=<7|15|30>` and the no-`days` case are unaffected.

## Test acceptance criteria

- The pre-existing failing regression test,
  `tests/test_runs_submit.py::test_run_new_submit_invalid_horizon_shows_human_readable_error`, now
  passes.
- New test, `tests/test_runs_horizon_summary.py::test_horizon_summary_out_of_range_days_rejected_with_422`
  — asserts `422` for `days=999` and `days=-1`, and that gateway-api is never called (mock handler
  raises `AssertionError` if hit).
- Full `services/dashboard-web` suite run with zero regressions.
- Not an ML/data-pipeline ticket (no `naive_first_engine`/model-adapter/feature-transform code touched)
  — no thesis-numbers regression check applicable.

## Review acceptance criteria (Tech Lead, personally verified)

- Read the diff directly: confirmed `_human_readable_run_request_error` is a small, non-generalized
  helper (not an error-formatting framework), and the Defect 2 guard is a single membership check, not
  a new validation layer — matches this ticket's explicit "keep it simple" instruction.
- Ran the two named tests directly and confirmed both pass.
- Ran the full `services/dashboard-web` suite directly (not the dev agent's self-report) — see Outcome.
- Confirmed neither fix touches leakage-sensitive logic, a lifecycle/state machine, or any rendered
  statistical number — consistent with the DASH-119/120/121 precedent for Tech-Lead-verification-only
  scope, but a `qa` subagent was still raised per this ticket's own explicit instruction (belt-and-
  braces re-verification of a QA-found defect, by QA itself).

## Documentation acceptance criteria

- This ticket file.
- `docs/tickets/README.md` — new sprint/ticket entry.
- `services/dashboard-web/README.md` — status line noting DASH-123's fix.

## Outcome

**Fix**: `_human_readable_run_request_error(exc)` added in `runs.py`, used in place of `str(exc)` in
`run_new_submit`'s `except (ValueError, ValidationError)` branch. `runs_horizon_summary` now raises
`HTTPException(422)` when `days` is set but not one of `HORIZON_SUMMARY_DAY_OPTIONS`.

**Tests**: `test_run_new_submit_invalid_horizon_shows_human_readable_error` now passes. New test
`test_horizon_summary_out_of_range_days_rejected_with_422` added and passes. At the time this ticket's
own fix was verified, the full suite showed 256 passed plus one failure in
`tests/test_runs_trend.py::test_trend_pages_through_more_than_one_hundred_runs` — confirmed unrelated
to this ticket (different route/root cause, not touched by this diff). That test was independently
fixed by DASH-122 landing concurrently in the same working tree; after both land together the full
suite is **267 passed**, 7 deselected (e2e), 0 failed (256 DASH-123 baseline + 1 QA-added edge-case
test for `days=0`/non-integer `days` + DASH-122's own fix/tests, not DASH-123's own scope).

**QA**: raised synchronously per this ticket's explicit instruction — GO verdict. QA independently
confirmed both fixes match acceptance criteria, added one further edge-case regression test
(`test_horizon_summary_days_zero_and_non_integer_rejected`, `days=0` and non-integer `days`, both
already correctly rejected by the existing guard/FastAPI's own type coercion — no code change needed),
and confirmed no leakage-sensitive, lifecycle, or positioning-language code was touched. See this
sprint/session's final report for the full QA writeup.
