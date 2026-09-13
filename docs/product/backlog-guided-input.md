# Backlog — guided input (dropdown-ification of fixed-value-set fields)

Source: `CLAUDE.md` (root — positioning constraints unaffected by this backlog; no story here touches
`naive_first_engine` or the leakage-aware protocol), `services/dashboard-web/README.md` (read in full —
every current config-input form field across this service), `services/dashboard-web/src/app/templates/
run_new.html` (read in full, including its inline `<script>` block), `services/dashboard-web/src/app/
templates/monitoring.html`, `_crawl_status_panel.html`, `settings_connectors.html`, `horizon_summary.html`,
`runs_trend.html` (read in full), `services/dashboard-web/src/app/routers/runs.py` (`_HORIZON_TO_DAY_LABEL`/
`_horizon_for_days`, `run_new_form`/`run_new_submit`), `services/dashboard-web/src/app/routers/operator.py`
(`POST /monitoring/reports/generate`), `docs/product/backlog-dataset-helpers.md` (DH-006 — a different
mechanism, suggested defaults into free-text fields, not duplicated here).

**Scope**: this is narrowly about converting a *specific* existing field, in the *current* codebase, that
already has a small, fixed, discoverable set of valid values, from free-text/number input to a
dropdown/select — not a generic form-configuration or client-side-validation framework. Per the user's own
"don't over-engineer" instruction, and per CLAUDE.md's DRY/module-boundary rules, only `dashboard-web`
templates are touched; no new backend endpoint is invented unless the option set doesn't already exist
somewhere it can be read from without new business logic.

This is a **new file**, not folded into `backlog-dataset-helpers.md` or `backlog-run-submission-safety.md`:
the one real story found here (GI-001) touches `monitoring.html`/`operator.py`, a different page/router than
either of those two backlogs' scope (run submission and dataset-quality helpers respectively), so it doesn't
fit cleanly under either title.

## Fields checked and their disposition

Every current free-text/number config-input field in this service was checked against "does a real,
queryable, small, fixed set of valid values exist for this today" — most do not, and are listed under
"Why not X" below rather than silently skipped.

## Stories

### GI-001 — Convert the "Generate a report" form's Run id field to a dropdown of the tenant's own runs [Should]
**As** the tenant using `monitoring.html`'s "Generate a report" trigger **I want** to pick an existing run
from a list instead of typing its id **so that** I can't submit a `run_id` that's misspelled, belongs to
another tenant, or doesn't exist — the exact failure mode this service's own README already discloses as a
known gap ("A `run_id` for a run that does not exist... surfaces as whatever non-`201` status... no
client-side existence check is performed before submitting").

Acceptance criteria:
- [ ] Exact current field: `run_id` on `monitoring.html`'s report-generation `<form>`
  (`<input type="text" id="run_id" name="run_id" required>`, `POST /monitoring/reports/generate`,
  `operator.py`). Exact current input type: free-text `<input type="text">`.
- [ ] New behavior: `GET /monitoring` (the page's existing render path, `operator.py`) fetches the tenant's
  own runs the same way `GET /runs` (`runs_list`, `runs.py`) already does — reusing that route's existing
  `_call_downstream`/`RunSummaryResponse` parsing (no second, near-identical `GET /runs` call implementation;
  implementation-plan.md section 9's DRY rule) — and passes them to `monitoring.html`, which renders
  `run_id` as a `<select>` with one `<option>` per run (label: id + status + created_at, so two runs aren't
  visually indistinguishable), replacing the free-text input.
- [ ] If the tenant has zero runs, the dropdown is not rendered blank/empty — the form falls back to (or
  keeps) the existing free-text input with an explanatory line ("No runs found yet — enter a run id
  directly, or submit a run first"), matching this service's own precedent of degrading to an honest empty
  state rather than hiding the whole feature (`datasets.html`'s "No ingested datasets yet" precedent).
- [ ] A `GET /runs` transport failure or non-200 while building this page degrades the same way — falls back
  to the free-text input, does not turn `GET /monitoring`'s otherwise-successful render into an error page
  (this trigger form is one section of a multi-section page, same non-blocking-degradation precedent
  `run_new_form`'s dataset-list fetch already sets).
- [ ] **Previously-submitted-value preservation (DASH-120 precedent)**: if a report-generation submission is
  rejected (e.g. a non-`201` from `reporting-service`/`gateway-api`) and the page re-renders with the
  submitted `run_id` still present, that value must still be shown/selected even if it no longer appears in
  the dropdown's current option list (run since deleted, or simply not in whatever page/limit of runs was
  fetched) — inject it as an extra, clearly-labeled `<option>` (e.g. "previously entered: <id> (not in your
  recent runs)") rather than silently dropping it to the placeholder, the same "never silently discard the
  user's selection on error redisplay" rule DASH-120 fixed for the Stored-dataset dropdown.
- [ ] No change to `POST /monitoring/reports/generate`'s accepted payload or to `GW-018`'s contract — this is
  a client-facing input-shape change only, not a new validation rule (the run's existence/ownership is still
  authoritatively checked downstream, exactly as today).

Rationale for priority: Should, not Must — this closes a disclosed, real usability gap (already named in
this service's own README "Known gaps" section) with a small, self-contained change confined to one already-
built page (`DASH-110`), not a new module or trigger; it's valuable but not blocking any other work.
Depends on: none (reuses `runs.py`'s already-shipped `GET /runs` call and `RunSummaryResponse` parsing)

## Why not X (fields considered and rejected)

- **`dataset_reference_field`** (`run_new.html`, free-text `<input type="text">`): rejected. Its own tooltip
  states the platform has no queryable list of a source's fields/columns — `DatasetSummaryResponse` (the only
  metadata `dashboard-web` has for a stored dataset) carries `source`/`row_count`/`earliest_timestamp`/
  `latest_timestamp` only, no field/column enumeration. The set of valid values is genuinely open-ended and
  source-specific, unknown until the data is actually loaded server-side — exactly the kind of field this
  task says not to force into a dropdown. If `ingestion-service` ever exposes a per-source field list (it
  doesn't today), this would become a real candidate — flagged for a future backlog, not built here.
- **`horizon`** (`run_new.html`, `<input type="number" min="1">`): rejected. `_HORIZON_TO_DAY_LABEL`/
  `_horizon_for_days` (`runs.py`) define a closed 168/360/720-hour (7/15/30-day) set, but that set belongs to
  a *different* feature (`/runs/horizon-summary`'s own filter, ADR-0007/FHS-002) which already renders as a
  set of links, not a free-text field needing conversion. The run-*submission* `horizon` field itself is a
  genuinely open-ended positive integer (a count of the selected dataset's own sampling steps, per ADR-0007
  finding (a) and DH-008's hint) — there is no fixed valid set to offer as a dropdown here, and forcing the
  horizon-summary's 7/15/30-day set onto it would misrepresent what the field actually accepts for any
  dataset whose sampling interval isn't hourly.
- **`tenant_id`** (`settings_connectors.html`, free-text `<input type="text">`): rejected for now, and
  already disclosed as a known gap in this service's own README ("no tenant directory/dropdown exists yet to
  look one up or validate it against"). No queryable tenant list exists until `SETUP-011` (tenant list/
  create/revoke admin endpoints, `docs/product/backlog-first-run-setup-and-ops.md`) ships — that ticket is
  the documented trigger for converting this field, not this backlog.
- **`dataset_reference_start`/`dataset_reference_end`** (`run_new.html`, `<input type="date">`) and the crawl
  trigger's **`since`** date field (`_crawl_status_panel.html`): rejected — a date range/cutoff is inherently
  open-ended (any date), not a fixed small set; a native date picker is already the appropriate guided input
  for this shape, not a dropdown.
- **`train_window`/`test_window`/`step`/`purge_gap_hours`** (`run_new.html`, numeric inputs): explicitly out
  of this story's scope per this task's own instruction — genuinely open-ended numeric tuning parameters with
  no fixed valid set; `docs/product/backlog-dataset-helpers.md`'s DH-006 (suggested defaults, a different
  mechanism) is the correct existing helper for these, not a dropdown.
- **`dataset_reference_source`** (`run_new.html`) and the trend page's **`metric`** selector (`runs_trend.html`):
  already dropdowns/selects today (`RSS-001`, `RAV-004`) — no work needed, listed here only so a future
  reader knows they were checked, not overlooked.

## Summary

| Priority | Count | IDs |
|---|---|---|
| Should | 1 | GI-001 |

Only one story met the bar this task set (a genuinely fixed, discoverable, currently-free-text field) after
checking every config-input field across this service's forms — consistent with the "keep it simple, don't
over-engineer" instruction: most candidate fields either already use a dropdown, or are genuinely open-ended
and were deliberately left alone rather than forced into an artificial constrained list.
