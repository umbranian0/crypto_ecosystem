# SETUP-034 — `dashboard-web`: make the existing operator login reachable by clicking through the UI

**Sprint**: 37. **Module**: `services/dashboard-web` only. **Status**: done.
**Priority**: Must. **Depends on**: none (`DASH-113`, Sprint 18, already shipped the backend
mechanism). **Blocks**: `SETUP-035` (same file/route, sequenced strictly after this ticket per
`docs/sprints/sprint-37.md`'s file-overlap note).

## Analysis

Covers `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-034` story in full. `DASH-113`
(Sprint 18) already shipped a real, distinct operator login flow — `GET`/`POST /operator-login`,
`OperatorSessionStore`, `require_operator_session`, the `operator_session_id` cookie — confirmed by
reading `services/dashboard-web/src/app/routers/operator.py` and
`src/app/dependencies/operator_session.py` directly. The gap is purely discoverability: nothing in
`base.html`/`login.html` links to it. This ticket does not touch `require_operator_session`,
`OperatorSessionStore`, or the existing `POST /operator-login` handler's logic (backlog AC,
binding) — templates, nav, and one new logout route only.

## Design

**Pattern**: none of implementation-plan.md section 7's patterns apply — pure UI wiring, same
non-goal `SETUP-030` held itself to for `infra`. The one existing pattern reused (not reinvented)
is Dependency Injection: the new `POST /operator-logout` route depends on
`OperatorSessionStoreDep`, the same DI seam `DASH-007`'s tenant `POST /logout` established one hop
over.

**Files touched** (scoped to `services/dashboard-web/src/app/`, per implementation-plan.md
section 3's module boundary):
- `src/app/templates/login.html` — a small, clearly secondary link to `/operator-login`
  ("Platform operator? Log in here"), styled/positioned so it reads as distinct from the tenant
  login form above it (backlog AC: avoid the "merge back together" `SETUP-010` warned against).
- `src/app/templates/base.html` — a second `<nav>` block, gated on
  `request.cookies.get('operator_session_id')` (independent of the existing tenant `<nav>` block's
  own `session_id` gate — both must be able to render simultaneously), linking to
  `/settings/tenants`, `/settings/environment`, `/monitoring`, plus a `POST /operator-logout`
  button mirroring the existing tenant `<form method="post" action="/logout">` shape exactly.
- `src/app/routers/operator.py` — new `POST /operator-logout` route, reusing
  `OperatorSessionStoreDep.delete`-style deletion and `Response.delete_cookie`, redirecting (303)
  to `/operator-login`.

**DRY check note**: grepped `src/app/routers/auth.py`'s existing `POST /logout` (`DASH-007`)
before writing this ticket — that handler is the exact template: read the session cookie, call the
store's `delete` method if present, clear the cookie via `RedirectResponse.delete_cookie`, redirect
303. `POST /operator-logout` must follow that same shape one-for-one, not invent a second
logout-handling style. `OperatorSessionStore` (`operator_session.py`) currently has no `delete`
method — `SessionStore` (tenant store, `dependencies/session.py`) does; add a `delete(session_id)`
method to `OperatorSessionStore` mirroring `SessionStore.delete` exactly (same signature/behavior:
pops the key if present, no-op/no-raise if absent) rather than duplicating tenant-session code or
reaching into the store's private dict from the router.

**Note for `/settings/environment`**: this route does not exist yet anywhere in the codebase
(confirmed by grep) — the nav link may 404 today. This ticket links to it per the backlog AC's
explicit route list; it does not scaffold the route itself (out of scope — no ticket in this
sprint plan builds `/settings/environment`). Document this as a disclosed, not silent, gap.

## Implementation acceptance criteria

- [x] `login.html` has a visible, secondary "Platform operator? Log in here" link to
  `/operator-login`, visually distinct from the tenant login form (not a second submit button
  inside the same `<form>`).
- [x] `base.html` renders a second, operator-scoped `<nav>` block when
  `operator_session_id` cookie is present, linking to `/settings/tenants`, `/settings/environment`,
  `/monitoring`, and a logout control — structurally parallel to, never merged with, the existing
  tenant nav block.
- [x] Both nav blocks render independently based on cookie presence (tenant-only, operator-only,
  both, neither all handled correctly, no `{% elif %}` chain that would suppress one when both
  cookies are present).
- [x] `POST /operator-logout` (`operator.py`) deletes the operator session (`OperatorSessionStore
  .delete`, new method mirroring `SessionStore.delete`), clears the `operator_session_id` cookie via
  `Response.delete_cookie`, redirects (303) to `/operator-login`.
- [x] Zero changes to `require_operator_session`, `OperatorSessionStore.get`/`.create`, or the
  existing `POST /operator-login` handler's logic.
- [x] Positioning check: no new copy implies trading/prediction capability.

## Test acceptance criteria

- [x] New/extended template-render test covering all four cookie-presence combinations (tenant
  only, operator only, both, neither) asserting the correct nav block(s) render — likely
  `tests/test_base_nav.py` (new) or an extension of an existing template test file.
- [x] Test for `POST /operator-logout`: session deleted from the store, cookie cleared, `303`
  redirect to `/operator-login`; and a no-session-present call is a safe no-op (no exception).
- [x] `login.html` render test asserts the `/operator-login` link is present.
- [x] Full existing dashboard-web suite re-run with zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms `require_operator_session`, `OperatorSessionStore.get`/`.create`, and
  `operator_login_form`/`operator_login_submit` are byte-for-byte unchanged (diff review).
- Confirms `OperatorSessionStore.delete` mirrors `SessionStore.delete`'s exact shape (DRY check),
  not a bespoke reimplementation.
- Confirms the four-combination nav test actually renders `base.html` with each cookie combination
  (not a shallow string-search substitute for a real template render).
- Confirms `login.html`'s new link is clearly secondary (copy/positioning), not a second tenant
  login affordance.
- Confirms no positioning-banned words introduced (grep against the same banned-word list other
  template tests use).

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md`: new section documenting the operator nav block and
  `POST /operator-logout`'s contract, and the disclosed `/settings/environment` link-to-nonexistent-
  route gap, cross-referencing this ticket.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-034` acceptance-criteria boxes
  checked, status marked done, pointer to this ticket.
- [x] `docs/tickets/README.md` gains a Sprint 37 entry for this ticket.
