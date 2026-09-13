# SETUP-015 — `dashboard-web`: Settings: read-only "Environment" panel

**Sprint**: 32. **Module**: `services/dashboard-web`. **Status**: done. **Priority**: Should.
**Depends on**: none. **Can run fully in parallel with**: `SETUP-011`→`SETUP-012` chain and
`SETUP-021` — disjoint new files, no shared template/router edited by any of those.

## Analysis

Backlog `SETUP-015`: a read-only panel showing non-secret connectivity facts (which services exist,
their configured hostnames/ports, links into `/monitoring`) — explicitly no secret value
(`DATABASE_URL`, passwords, API keys, `OPERATOR_TOKEN`) ever rendered, and structurally no POST/edit
route (read-only enforced by absence of a route, not by omitting a button).

**DRY check** (grepped `src/app/dependencies/downstream.py`, `src/app/routers/*.py` before writing
this ticket): the only existing env-var readers are `get_gateway_api_url` (`GATEWAY_API_URL`) and
`cookie_secure`/`OperatorSessionStore`'s reads of `DASHBOARD_COOKIE_SECURE`. No existing "list all
configured service endpoints" helper exists — this ticket introduces the first one, scoped to
non-secret facts only.

## Design

**Pattern**: none from implementation-plan.md section 7 is forced here — this is a plain read-only
render, not a DI seam, Repository, or Strategy case.

**Files touched** (scoped to `services/dashboard-web` only):
- `src/app/routers/settings_environment.py` (new module, same "one module per Settings concern"
  precedent as `settings.py`/`settings_tenants.py`): `GET /settings/environment`
  (`OperatorTokenHeaderDep`, same gate `settings.py`/`settings_tenants.py` already use — this page is
  operator-only, not a tenant page). Reads **only** non-secret facts: `GATEWAY_API_URL` (via the
  existing `get_gateway_api_url()`, reused not reimplemented), a literal list of this platform's known
  service names (`gateway-api`, `validation-service`, `reporting-service`, `ingestion-service`,
  `dashboard-web` itself) with their env-var *names* (not values) that would configure each, and a
  link to `/monitoring` for live status. **No route reads `DATABASE_URL`, `OPERATOR_TOKEN`, any
  `*_API_KEY`/password env var, or any per-service internal DB/Redis URL — this must be true by
  construction (no such `os.environ.get` call anywhere in this file), not merely by omitting it from
  the template context.**
- `src/app/templates/settings_environment.html` (new) — non-secret facts table, explicit "read-only —
  change via `infra/.env` and restart the stack, not this page" label, a link to `/monitoring`.
- `services/dashboard-web/README.md` — new "Settings: environment panel (SETUP-015)" section.

**No shared nav partial introduced** (same decision `SETUP-012` makes) — this page cross-links to
`/settings/tenants` and `/settings/connectors` via a plain paragraph, not a shared nav template.

## Implementation acceptance criteria

- [x] `/settings/environment` requires `OperatorTokenHeaderDep` (operator session), same gate as
  `/settings/connectors`/`/settings/tenants`.
- [x] Shows only non-secret connectivity facts: known service names, their configurable env var
  *names* (not values), and `GATEWAY_API_URL`'s actual current value (this one is non-secret — a
  hostname/port, not a credential) — links to `/monitoring` for live status.
- [x] No secret env var value (`DATABASE_URL`, any password, any API key, `OPERATOR_TOKEN`) is ever
  read by this route or rendered by this template, in any form (not redacted, not partially masked —
  never sent to the template context at all).
- [x] No `@router.post`/`@router.put`/`@router.delete` route exists anywhere in
  `settings_environment.py` — read-only is enforced structurally.

## Test acceptance criteria

- [x] `tests/test_settings_environment.py` (new): unauthenticated (no operator session) → `303`;
  authenticated → page renders the expected non-secret facts; a static/source-level test (grep the
  module source in-test, or assert on a captured `os.environ` mock that only the allow-listed var
  names are ever read) proving no secret env var name/value appears in the rendered HTML even when a
  realistic `DATABASE_URL`/`OPERATOR_TOKEN` is set in the test's own environment.
- [x] A banned-word test for positioning (CLAUDE.md), same convention as other pages.
- [x] Full dashboard-web suite run, zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Reads `settings_environment.py` directly, confirms no secret env var name is ever passed to
  `os.environ.get`/read in any form.
- Confirms no POST/edit route exists in this file at all (not merely hidden from the template).
- Confirms the "read-only, restart to change" language is present and not misleading (no field looks
  editable).
- Re-runs the full suite, confirms zero regressions.

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md` gets a "Settings: environment panel (SETUP-015)" section
  documenting exactly which facts are shown and the explicit list of what is deliberately never shown.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-015` acceptance boxes checked, status
  marked done, citing this ticket.
