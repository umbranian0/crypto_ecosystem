# SETUP-012 — `dashboard-web`: Settings → Tenants page

**Sprint**: 32. **Module**: `services/dashboard-web`. **Status**: done. **Priority**: Must.
**Depends on**: `SETUP-011` (must be implemented/verified first — this ticket calls its endpoints).
**Can run in parallel with**: `SETUP-021` (disjoint files: this ticket touches `settings_tenants.py`/
`settings_tenants.html`; `SETUP-021` touches `operator.py`/`monitoring.html`).

## Analysis

Backlog `SETUP-012`: an operator-only Settings page listing tenants/keys, with create (one-time-reveal)
and revoke actions, reusable-not-duplicated one-time-reveal component per `SETUP-003`'s own wizard
precedent, gated by the operator credential (`SETUP-010`'s `require_operator_session` +
`OperatorTokenHeaderDep`), never a tenant session cookie.

**Read directly before writing code**: `src/app/routers/settings.py` (`DASH-112`,
`/settings/connectors`) is the existing precedent for an operator-gated Settings sub-page — reuses
`OperatorTokenHeaderDep` (`app.dependencies.operator_session`), `GatewayApiUrlDep`, and
`runs.py`'s `_call_downstream`/`_render_error_for_status`. `src/app/templates/base.html`'s nav is
gated on the **tenant** session cookie only (`{% if request.cookies.get('session_id') %}`) — there is
no operator-area nav partial today, and `settings_connectors.html` has no nav of its own. This ticket
does **not** invent a shared operator nav partial (avoids the file-overlap risk the sprint plan flags
for a hypothetical shared Settings nav element) — `settings_tenants.html` and `settings_connectors.html`
instead get one plain cross-link paragraph each to the other Settings page(s), no shared template file.

## Design

**Pattern**: DI (`Depends()`), reusing `OperatorTokenHeaderDep`/`GatewayApiUrlDep`/
`_call_downstream`/`_render_error_for_status` — no new pattern.

**Files touched** (scoped to `services/dashboard-web` only):
- `src/app/routers/settings_tenants.py` (new module — disjoint from `settings.py`, mirroring that
  file's own "one fresh module per distinct Settings concern" precedent so this ticket's diff never
  touches `settings.py`):
  - `GET /settings/tenants` (`OperatorTokenHeaderDep`): calls `SETUP-011`'s `GET /tenants`, renders a
    table of tenants + their keys (metadata only).
  - `POST /settings/tenants` (`OperatorTokenHeaderDep`): form field `tenant_name`, calls `SETUP-011`'s
    `POST /tenants`, renders the one-time-reveal confirmation (extracted shared partial, see below),
    then a link back to `GET /settings/tenants`.
  - `POST /settings/tenants/{tenant_id}/api-keys/{key_id}/revoke` (`OperatorTokenHeaderDep`): calls
    `SETUP-011`'s revoke endpoint, returns an HTMX fragment (`_tenant_row.html` or a
    `_revoke_result.html`, whichever the dev finds renders the list update most simply) so the table
    re-renders that key's `revoked_at` with no manual page reload — same HTMX
    `hx-post`/`hx-target`/`hx-swap` mechanism `operator.py`'s `DASH-110` trigger actions already
    established, reused, not reinvented.
- `src/app/templates/_one_time_reveal.html` (new shared partial, extracted from the existing
  one-time-reveal confirmation markup in `setup_key_reveal.html` — **read `setup_key_reveal.html`
  first** to confirm its exact current markup before extracting, don't guess the shape). Both
  `setup_key_reveal.html` (`SETUP-003`) and this ticket's own create-tenant confirmation render use
  the shared partial, parameterized by the label ("tenant" vs. whatever `SETUP-003`'s copy says) and
  the raw key value — one component, not two near-identical pages/blocks (backlog's own explicit DRY
  requirement for this story).
- `src/app/templates/settings_tenants.html` (new) — table + create form + revoke buttons.
- `services/dashboard-web/README.md` — new "Settings: tenant management (SETUP-012)" section.

**DRY check note** (grepped `src/app/routers/settings.py`, `src/app/templates/setup_key_reveal.html`
before writing this ticket): `OperatorTokenHeaderDep`/`_call_downstream`/`_render_error_for_status`
already exist and are reused directly; the one-time-reveal markup is extracted rather than copied a
second time, per the ticket's own binding Design decision above.

## Implementation acceptance criteria

- [x] `/settings/tenants` (all three routes) requires `OperatorTokenHeaderDep` — a tenant's own
  `session_id` cookie cannot reach this page (proven by test, not just by construction).
- [x] Lists tenants + keys, key values shown only as metadata (`id`, `created_at`, `revoked_at`) —
  never a raw or partially-masked key once creation is past.
- [x] "Create tenant" shows the new raw key exactly once via the shared `_one_time_reveal.html`
  partial (not a second near-identical page/block).
- [x] "Revoke" re-renders the affected row's `revoked_at` via an HTMX fragment swap, no manual page
  refresh.
- [x] Positioning check: no copy on this page implies trading/prediction capability (CLAUDE.md) — the
  page describes tenants/keys as "validation-run" access credentials only.

## Test acceptance criteria

- [x] `tests/test_settings_tenants.py` (new): unauthenticated (no operator session) → `303` to
  `/operator-login`; a real operator session → list renders; create → one-time-reveal renders the raw
  key exactly once and it is absent from any subsequent render (e.g. a follow-up `GET`); revoke →
  fragment reflects `revoked_at`, list page's own row (on a fresh `GET`) also reflects it.
- [x] A banned-word test scans `settings_tenants.html`/`_one_time_reveal.html` for
  prediction/forecast/signal/recommendation language, mirroring `datasets.html`'s/`run_detail.html`'s
  existing convention.
- [x] `setup_key_reveal.html`'s existing tests still pass unmodified after the extraction (proves the
  refactor didn't change `SETUP-003`'s own rendered output).
- [x] Full dashboard-web suite (`.venv\Scripts\python.exe -m pytest -q`) run, zero regressions —
  267 passed, 7 deselected (up from 257 passed, 7 deselected baseline).

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms `/settings/tenants` truly cannot be reached with a tenant `session_id` cookie (reads the
  dependency chain, not just the test file).
- Confirms the one-time-reveal partial is genuinely shared (one file, two call sites), not a
  copy-pasted near-duplicate under a different name.
- Confirms no raw/full key value is ever rendered on any page after the initial creation response.
- Re-runs the full suite, confirms zero regressions.

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md` gets a "Settings: tenant management (SETUP-012)" section,
  cross-referencing `SETUP-011`'s gateway-api contract and noting the shared one-time-reveal partial
  now used by both this page and `SETUP-003`'s wizard.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-012` acceptance boxes checked, status
  marked done, citing this ticket.
