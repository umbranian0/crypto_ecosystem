# DASH-113 — Minimal `/monitoring` page + operator-token session gate (slice of `SETUP-012`/`020`)

**Sprint**: 18. **Module**: `services/dashboard-web`. **Status**: done. **Priority**: Must.
**Depends on**: `GW-021`, `GW-022`. **Blocks**: `DASH-109`, `DASH-110`, `DASH-112`.

## Analysis
Per the requester's resolution: build only the minimal surface `DASH-109`/`110`/`112` need — a
`/monitoring` page rendering `GW-022`'s aggregate health, and an operator-token gate reusable by any
`/settings/*` route. Not the full `SETUP-003` setup wizard, not `SETUP-012`'s full tenant-management UI.

## Design
Files: new `services/dashboard-web` routes — `GET /operator-login` (enter `OPERATOR_TOKEN`, stored in a
signed session cookie on success, same session mechanism `DASH-002`'s tenant login already
established — reused, not reinvented), `GET /monitoring` (calls `GW-022`, renders one row per service),
a `require_operator_session` dependency gating any `/settings/*` route. **DRY check**: reuses
`DASH-003`'s existing session-to-downstream-header DI seam and cookie-signing mechanism.

## Implementation acceptance criteria
- [x] `/operator-login`: token form → on success, sets a signed session marker distinct from a tenant's
  own session cookie (never satisfies `DASH-003`'s tenant-session dependency, and vice versa).
- [x] `/monitoring`: one row per service (name, status) from `GW-022`; unreachable aggregate call itself
  renders the existing `error.html`/`_render_error_for_status` convention (`DASH-004` precedent).
- [x] `require_operator_session` dependency used by any future `/settings/*` route (`DASH-112` is its
  first real consumer) -- the gate itself is built and tested; no `/settings/*` route is built by this
  ticket (out of scope, `DASH-112`'s own work).

## Test acceptance criteria
- [x] Operator login success/failure; `/monitoring` all-healthy/degraded/unreachable rendering
  (mocking `GW-022`'s response); a tenant's own session cannot reach an operator-gated route.

## Review acceptance criteria (Tech Lead verifies personally)
- Confirms operator session and tenant session are structurally distinct cookies/mechanisms.
- Confirms positioning check: no copy implies trading/prediction capability.

## Documentation acceptance criteria
- [x] `services/dashboard-web/README.md` documents `/operator-login`/`/monitoring`, states plainly this
  is the minimal slice of `SETUP-003`/`012`/`020` pulled into this sprint for `DASH-109`/`110`/`112`'s
  sake — the full setup wizard and tenant-management UI remain the sibling backlog's own scope.
