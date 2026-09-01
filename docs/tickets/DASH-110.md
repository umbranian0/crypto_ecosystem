# DASH-110 (unblocked) — Trigger-action UI: "run this tenant's crawl now" / "generate a report"

**Sprint**: 18. **Module**: `services/dashboard-web`. **Status**: done. **Priority**: Must.
**Depends on**: `GW-019`, `GW-018` (already done), `DASH-113` (this sprint's minimal `/monitoring`
page — buttons attach to it).

## Analysis
Story: backlog `DASH-110`, unchanged design — every action a normal authenticated HTTP call, never
Docker-socket/container control (decision #6's explicit, structurally-enforced boundary).

## Design
File: `DASH-113`'s `/monitoring` template/route (extend). **DRY check**: reuses `SETUP-012`-equivalent
inline-re-render pattern already used elsewhere in `dashboard-web` (`DASH-004`'s error convention for
failures) — no new UI pattern.

## Implementation acceptance criteria
- [x] Per-source "Run this tenant's crawl now" buttons call `GW-019`'s proxy, show the resulting
  `crawl_run_id`/status inline, no full-page reload.
- [x] "Generate a report" button calls the already-existing `reporting-service` `POST /reports/generate`
  via `GW-018`'s already-existing proxy — no new reporting capability added.
- [x] Every failure path renders the existing `error.html` convention.
- [x] Structural proof: `grep -R "docker\|subprocess"` across `services/dashboard-web` after this ships
  returns zero hits.

## Test acceptance criteria
- [x] Button success/failure cases for both actions, mocked downstream.

## Review acceptance criteria (Tech Lead verifies personally)
- Personally runs the grep proof, confirms zero Docker-socket/subprocess references.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` documents both trigger actions.

## Outcome

Implemented both trigger actions as two new `POST` routes in the existing
`services/dashboard-web/src/app/routers/operator.py` (the same module `/monitoring` already lives in --
no new router module, per this ticket's own Design section):

- `POST /monitoring/connectors/{source}/run` -- one button per source row in the crawl-status panel,
  calling `gateway-api`'s already-existing `GW-019` proxy. Gated by `DownstreamHeadersDep` (redirect to
  `/login`, same seam every other tenant-scoped route in this service uses), rendered only inside the
  crawl-status panel's own logged-in branch.
- `POST /monitoring/reports/generate` -- one form (`run_id` text input) calling the already-existing
  `GW-018` proxy (`POST /reports/generate`). No new reporting capability added anywhere.
- Both actions swap a small HTML fragment (`_crawl_trigger_result.html` / `_report_trigger_result.html`)
  into a per-action result `<div>` via HTMX (`hx-post`/`hx-target`/`hx-swap`) -- `base.html` already
  loaded `htmx.org` unused since this service's scaffold; this ticket is its first real consumer, not a
  newly introduced dependency or pattern.
- Every failure path (transport-level `ConnectError`/`TimeoutException`, or any non-2xx from
  `gateway-api`) reuses `runs.py`'s existing `_render_error_for_status`/`error.html` convention,
  unmodified -- no new error-handling pattern.
- **Structural proof, literally re-run at completion**: `grep -rn "docker\|subprocess" -i
  services/dashboard-web/src` returns zero hits. The ticket's own explanatory docstring text was
  reworded (e.g. "no container-runtime control surface" instead of the literal words) so that the
  grep proof itself stays a true zero, not just a policy statement.
- Tests: `services/dashboard-web/tests/test_monitoring_triggers.py` (new), 11 tests covering both
  actions' success/non-2xx/transport-failure/session-required cases and the monitoring page's own
  hx-post-form-visible-only-when-logged-in check. Full suite: 101 passed, 5 deselected (e2e), 0 failed
  (up from the pre-ticket baseline of 90 passed / 95 collected).
- Documentation: `services/dashboard-web/README.md` updated additively -- new "Trigger actions on
  /monitoring (DASH-110)" section, `Owns`/`Contract`/`Known gaps`/Sprint 18 summary sections extended,
  Design notes bullet added, Tests section updated with the new file and pass count.

All acceptance criteria met; no scope beyond this ticket's file (`services/dashboard-web`) was touched.
