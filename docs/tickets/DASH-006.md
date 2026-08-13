# DASH-006 — Submit-a-run form

**Status: done**

## Analysis
Story: DASH-006 (Must), depends on DASH-003 and DASH-004 (redirect target on success — DASH-004 must
be fully done first, not run in parallel, per sprint-11.md's own sequencing correction). Backlog
acceptance criteria: `GET /runs/new` renders a form matching gateway-api's real `POST /runs` request
shape exactly (`GW-008`): `dataset_id` (str), `dataset_reference` (supports validation-service's
interim inline-payload/local-file modes), `horizon` (>=1), `purge_gap_hours` (>=0),
`train_window`/`test_window`/`step` (>0); `POST /runs/new` submits via DASH-003's headers to
gateway-api's real `POST /runs`, on `201` redirects to DASH-004's detail page for the returned id; no
new run-execution logic/config default/shortcut that could let a submitted run skip the purge gap or
mandatory naive baselines — pass-through UI only; `422` redisplays the form with the specific error,
client-side checks mirror server-side but don't replace it; after redirect, DASH-004 reflects the
run's real initial status (running/completed/failed per `VS-006`/`VS-012`) — no fabricated optimistic
state; tests per backlog AC6.

**Exact request shape, confirmed directly**: `naive_first_common.contracts.RunRequest`: `dataset_id:
str`, `dataset_reference: dict`, `horizon: int (ge=1)`, `purge_gap_hours: int (ge=0)`, `train_window:
int (gt=0)`, `test_window: int (gt=0)`, `step: int (gt=0)`. `dataset_reference` is a `dict`, not a
flat field — `validation-service`'s `DatasetSource` (`VS-005`) accepts either an inline
timestamp/value payload or a local CSV file path reference (confirmed by reading
`services/validation-service/README.md`'s "Dataset access (VS-005)" section directly). The form must
therefore expose both interim modes, not invent a third: a "local file path" text input (maps to
`dataset_reference = {"path": <value>}` — confirm the exact key `InlineOrLocalFileDatasetSource`
expects by reading `services/validation-service/src/app/dataset_source.py` directly before writing
the form, do not guess the dict key) and, minimally, a toggle or second textarea for an inline
payload if `dataset_source.py`'s inline mode has a materially different shape — whichever the real
code expects, copied exactly, not approximated.

**Confirmed directly against `services/validation-service/src/app/dataset_source.py`**:
`InlineOrLocalFileDatasetSource.load` accepts a dict with either a `"path"` key (local CSV file path)
or an `"inline"` key, whose value is either a list of `[timestamp, value]` pairs or a
`{"timestamps": [...], "values": [...]}` dict. The form exposes exactly these two modes as two text
fields (`dataset_reference_path`, `dataset_reference_inline`), not a third.

## Design
Pattern: **Dependency Injection** only (DASH-003's seam) — this is pass-through UI, no Strategy/
Factory/Template Method applies (the actual Template Method — split -> baseline -> metrics -> DM test
— lives in `naive_first_engine`/`validation-service`, untouched by this ticket; this ticket's own
"no shortcut" AC exists precisely so nothing here ever gets a chance to bypass that fixed order).
Files: `src/app/routers/runs.py` (same file DASH-004 created — sequential edit, not parallel, exactly
as sprint-11.md's sequencing decision requires: DASH-004 fully done first), `src/app/templates/
run_new.html` (new, extends `base.html`).

Handler flow: `GET /runs/new` renders the form (no gateway-api call — a pure static form render).
`POST /runs/new` -> resolve `headers: DownstreamHeadersDep`, `base_url: GatewayApiUrlDep` -> build a
`RunRequest` from the submitted form fields (client-side numeric-range checks mirrored in the
template via HTML5 `min`/`required` attributes, but the *authoritative* validation is
`RunRequest`'s own Pydantic constraints plus whatever `422` gateway-api itself returns — do not
duplicate gateway-api's own validation logic beyond what's needed to construct the request object) ->
`httpx.post(f"{base_url}/runs", json=..., headers=headers)` -> on `201`, parse `RunResponse` (`{id,
status}`, imported from `naive_first_common.contracts`, same DRY point as DASH-004) and redirect
(`303`) to `/runs/{id}` (DASH-004's route) — **do not render any status text on this page before
redirecting**; the redirect target (DASH-004) is the single source of truth for the run's real status,
so there is no "optimistic" state to fabricate here at all, structurally satisfying the backlog's "no
fabricated optimistic state" AC by construction rather than by convention. On `422` from gateway-api,
redisplay `run_new.html` with gateway-api's own validation error message(s) and the submitted values
repopulated (this is the one form field DASH-002 explicitly forbids repopulating for the API key —
`RunRequest`'s fields are not secrets, repopulating them here is fine and expected UX). On
`httpx.ConnectError`/`TimeoutException` or `502`/`504`, reuse DASH-004's `error.html` template
(**do not create a second error template** — DRY, per implementation-plan.md section 9, checked
explicitly here since this is the second place a transport failure can occur).

DRY check: grepped `src/app/routers/runs.py` (DASH-004's file — this ticket edits it, does not
recreate it) and `src/app/templates/error.html` (DASH-004's — reused, not duplicated) before writing.

**Actual implementation note**: `GET /runs/new`/`POST /runs/new` are registered *before*
`GET /runs/{run_id}` in the router — FastAPI/Starlette match routes in registration order, so
`/runs/{run_id}` would otherwise swallow `/runs/new` as `run_id="new"`. DASH-004's `_fetch` helper was
generalized (renamed `_call_downstream`, taking a bound `httpx.Client` method instead of being
GET-only) so the new `POST /runs` call reuses the exact same transport-failure translation rather than
a second near-identical try/except — a deliberate DRY refactor of DASH-004's own code, not a new
pattern. `GET /runs/new` also depends on `DownstreamHeadersDep` (unused beyond enforcing the session
check) even though it makes no downstream call itself, since the README already documents this route
as one every future authenticated route depends on, and the form is only reachable once logged in
(matches `POST /login`'s redirect target).

## Implementation acceptance criteria
- [x] `GET /runs/new` renders a form with exactly `dataset_id`, `dataset_reference`'s real
  interim-mode field(s) (confirmed against `validation-service/src/app/dataset_source.py` directly),
  `horizon`, `purge_gap_hours`, `train_window`, `test_window`, `step` — no extra field, no field
  omitted, no default value that could skip the purge gap (e.g. no `purge_gap_hours` default of `0`
  pre-filled in a way that looks like a recommended value — leave it blank or use gateway-api's own
  `ge=0` as the only constraint communicated).
- [x] `POST /runs/new` submits via `DownstreamHeadersDep`'s headers to gateway-api's real `POST
  /runs`; `201` redirects to `/runs/{id}`.
- [x] `422` redisplays `run_new.html` with the specific error, submitted values repopulated.
- [x] `201` with `status: "failed"` in the body still redirects to `/runs/{id}` (DASH-004 renders the
  failure there, per its own `failure_reason` field) — distinguishable at that page from a `502`/`504`
  transport failure (which never reaches this far, since a transport failure isn't a `201` at all).
- [x] No field/default in this ticket's code can cause a submitted run to skip the purge gap or naive
  baselines — this is a correctness bug if violated, not a style choice (re-stated from the backlog
  verbatim since it's this ticket's single highest-stakes constraint).

## Test acceptance criteria
- [x] `tests/test_runs_submit.py` (mocked gateway-api): valid submit redirects to `/runs/{id}`; `422`
  redisplays the form with the specific error; a `201` with `status: "failed"` redirects to
  `/runs/{id}` and is distinguishable there (via DASH-004's rendering of `failure_reason`) from a
  `502`/`504` case (which never redirects at all, rendering `error.html` in place instead).
- [x] Run via `.venv\Scripts\python.exe -m pytest -q` (or `uv run pytest`), confirm pass, paste output.

## Review acceptance criteria
- [x] Tech Lead personally reads the submitted-form -> `RunRequest` construction path end to end,
  confirming no default/shortcut/hardcoded value could cause `purge_gap_hours` or the baseline set to
  be skipped or altered from what the tenant actually submitted — this is checked as a correctness
  review, not just a passing-test review, per this ticket's own stated stakes. Confirms `error.html`
  is reused, not duplicated (via `git status`/diff — no new `error.html`-shaped file appears).

**Tech Lead review (2026-08-12)**: read `runs.py`'s `run_new_submit` handler end to end, this
ticket's single highest-stakes point. Confirmed: `dataset_reference` is built directly from whichever
of the two submitted text fields is non-blank, with no third mode and no injected/overridden value;
`RunRequest(...)` is constructed with every numeric field taken verbatim from the submitted form
(`int(horizon)`, `int(purge_gap_hours)`, etc.) — no default substituted anywhere, no field silently
dropped or coerced to a "safe" value. `purge_gap_hours` has no pre-filled default in `run_new.html`
(confirmed by reading the template — the `value=` attribute is empty unless `values` was passed back
on a `422` redisplay). The submitted `RunRequest.model_dump()` is sent to gateway-api's real `POST
/runs` unmodified — nothing here can cause a run to skip the purge gap or the mandatory naive
baselines, since this handler never touches `naive_first_engine`/`validation-service`'s own protocol
code, only constructs the wire request. Confirmed `error.html` is reused (no second error-shaped
template exists in `src/app/templates/` — `git status`/`ls` shows only `run_new.html` as new).
Confirmed the disclosed route-ordering fix (`/runs/new` registered before `/runs/{run_id}`) is real
and necessary (FastAPI/Starlette matches path patterns in registration order) and the `_call_downstream`
generalization is a genuine DRY improvement over DASH-004's original `_fetch`, not a behavior change
(re-verified DASH-004's own four failure-path tests still pass unchanged). Re-ran the suite
independently: `.venv\Scripts\python.exe -m pytest -q` from `services/dashboard-web` -> **34 passed**,
0 failed, matching the dev agent's reported output exactly.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md`'s "Contract" section gains a line confirming this route
  submits to gateway-api's real `POST /runs` via the shared `RunRequest`/`RunResponse` models, with
  the same version-sync caveat as DASH-004's entry.

## Outcome

Implemented by dev subagent. `GET /runs/new` renders a form matching `RunRequest`'s exact fields (plus
the two `dataset_reference` interim-mode fields, confirmed directly against
`services/validation-service/src/app/dataset_source.py`); no field is pre-filled with a default value.
`POST /runs/new` builds `dataset_reference` from whichever of `dataset_reference_path`/
`dataset_reference_inline` is non-blank (`{"path": ...}` or `{"inline": <parsed JSON>}`, exact key
names from `InlineOrLocalFileDatasetSource.load`), constructs a `RunRequest`, and submits it to
gateway-api's real `POST /runs` via `DownstreamHeadersDep`/`GatewayApiUrlDep`. On `201` (any `status`
value, including `"failed"`) it redirects (`303`) to `/runs/{id}` without rendering any status text
itself. On `422` (either from local `RunRequest`/JSON parsing or forwarded from gateway-api) it
redisplays `run_new.html` with the specific error and submitted values repopulated. Transport failures
and `502`/`504` reuse the existing `error.html` template — no second template created.

Files changed:
- `services/dashboard-web/src/app/routers/runs.py` (DASH-004's file, edited in place — added
  `GET /runs/new`/`POST /runs/new`, generalized `_fetch` into `_call_downstream`).
- `services/dashboard-web/src/app/templates/run_new.html` (new).
- `services/dashboard-web/tests/test_runs_submit.py` (new, 12 tests).
- `services/dashboard-web/README.md` ("Contract" section, "Design notes", "Known gaps", new
  "Submit a run (DASH-006)" section, status line).

Test results (`.venv\Scripts\python.exe -m pytest -q`, run from `services/dashboard-web`): all 34
tests pass (12 new DASH-006 tests + 22 pre-existing), 0 failures.

Tech Lead independent re-run (2026-08-12): 34 passed, 0 failed -- matches exactly.

All Implementation, Test, Review, and Documentation acceptance criteria met.
