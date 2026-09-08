# SETUP-003 — `dashboard-web`: browser-based setup wizard

**Sprint**: 29. **Module**: `services/dashboard-web`. **Status**: done. **Priority**: Must.
**Depends on**: `SETUP-002` (calls `/setup/initialize`), `SETUP-030` (needs a real Compose
`gateway-api` container to test against realistically, per the sprint plan).
**Blocks**: `SETUP-004` (opens the browser at what this ticket builds).

## Analysis

Per `backlog-first-run-setup-and-ops.md`'s `SETUP-003` story: this is the actual user-facing
deliverable of the epic — without it, "browser-based, not a CLI script" is just an API a human would
still have to `curl`. CLAUDE.md's core positioning constraint applies directly here (this is the first
page a brand-new operator sees): copy must describe what's being created as a "tenant" and an "API key
for validation runs" only — never anything implying trading/prediction capability. The sprint's own
DoD is explicit and non-negotiable on this point.

## Design

**Pattern**: DI (FastAPI `Depends()`), reusing `dashboard-web`'s existing `GatewayApiUrlDep`/
`get_gateway_api_url` seam (`DASH-003`) for the outbound call to `gateway-api`'s new `/setup/*`
endpoints — no new HTTP-client mechanism. This route family is deliberately **not** gated by
`DownstreamHeadersDep` (DASH-003's tenant-session dependency) or `require_operator_session`
(DASH-113's operator-session gate) — there is no session of either kind yet on a fresh install, the
same chicken-and-egg reasoning `SETUP-001`/`SETUP-002` already applied on the `gateway-api` side.

**Files touched** (scoped to `services/dashboard-web` only):
- `src/app/routers/setup.py` (new router module, following the established "one module per distinct
  concern" precedent `operator.py`/`settings.py` already set) — `GET /setup` (renders the tenant-name
  form or redirects to `/login` if already initialized), `POST /setup` (calls `gateway-api`'s `POST
  /setup/initialize`, renders the one-time key-reveal confirmation on success).
- `src/app/main.py` — root route (`GET /`) gains the `initialized` branch: calls `gateway-api`'s `GET
  /setup/status` first; `initialized: false` → redirect to `/setup`, `initialized: true` → existing
  behavior (redirect to `/login`, unchanged). Registers `setup.router` alongside the existing
  `auth`/`operator`/`runs`/`settings` router imports.
- `src/app/templates/setup.html` (new) — the tenant-name form.
- `src/app/templates/_setup_key_reveal.html` (new partial) — the one-time key-reveal confirmation,
  with the "copy this now — it cannot be recovered" warning, followed by a link to `/login`. **DRY
  check**: this is the same one-time-reveal shape `SETUP-012` (next sprint, Settings → Tenants "create
  tenant" flow) will need again — build this as a reusable partial from the start (parameterized on
  `tenant_name`/`api_key`, no `/setup`-specific copy baked into markup that a future shared partial
  would need to strip back out) rather than a page-specific template that gets duplicated next sprint.
- `src/app/routers/auth.py` or wherever `GET /login` currently lives — no change needed if `/setup`
  visited post-initialization simply redirects to `/login` (303) rather than re-rendering; confirm at
  implementation time whether this belongs in `setup.py`'s own `GET /setup` handler (preferred — keeps
  the redirect decision local to the route that needs it) rather than a shared dependency.

**DRY check note** (grepped `src/app/routers/`, `src/app/dependencies/` before writing this ticket):
`_call_downstream`/`_render_error_for_status` (`runs.py`) are the existing transport-failure-to-
`error.html` helpers every other route in this service already shares — this ticket's `/setup` routes
reuse them for `gateway-api` being unreachable, rather than inventing a third near-identical
try/except.

## Implementation acceptance criteria

- [x] `GET /` checks `gateway-api`'s `GET /setup/status`; `initialized: false` redirects to `/setup`
  instead of `/login`.
- [x] `GET /setup` renders a tenant-name form; `POST /setup` calls `gateway-api`'s `POST /setup/
  initialize`.
- [x] On success, the raw API key is shown exactly once with the "copy this now — it cannot be
  recovered" warning, followed by a link to `/login` — the raw key is never logged, never placed in a
  URL/redirect `Location` header, matching `DASH-002`'s existing raw-key-handling discipline for
  login.
- [x] If `/setup` is visited when `gateway-api` reports `initialized: true`, it redirects straight to
  `/login` — no form re-render, and `gateway-api`'s `409` from a stray `POST /setup` in that state is
  never surfaced as a user-facing error (the redirect on `GET` prevents that path from being reached
  through the UI at all).
- [x] Positioning check: the wizard's copy uses only "tenant" and "API key for validation runs" —
  banned-word scan (mirroring `datasets.html`'s/`run_detail.html`'s existing
  `test_..._has_no_banned_positioning_words` pattern) covers `setup.html`/`_setup_key_reveal.html` for
  "prediction," "forecast," "signal," "trading," "recommendation."

## Test acceptance criteria

- [x] Unit tests (mocked `gateway-api` transport, mirroring `test_operator_login.py`'s/`test_auth.py`'s
  existing pattern): fresh install (`initialized: false`) → `GET /` redirects to `/setup`; already-
  initialized (`initialized: true`) → `GET /` redirects to `/login` (unchanged); `POST /setup` success
  renders the key-reveal page with the fixture's real key; `POST /setup` when already initialized
  (simulating the `409`, reachable only via a direct `POST`, not the normal UI flow) is handled
  gracefully, not as a raw error page.
- [x] Extends the existing Selenium E2E suite (`DASH-009`, `src/app/tests/e2e/`) with a new flow: fresh
  stub `gateway-api` (zero tenants) → wizard shown at `/` → submit tenant name → key displayed once →
  follow the `/login` link → log in successfully with that key.
- [x] Banned-positioning-word test for both new templates.
- [x] `uv run pytest -q` run in full (unit + e2e), zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Reads `setup.html`/`_setup_key_reveal.html` directly for positioning-rule compliance — not merely
  trusting the automated banned-word scan.
- Confirms the raw key never appears in a URL, redirect `Location` header, or log line (reads the
  route handler, same discipline `DASH-002`'s login flow was held to).
- Confirms `_setup_key_reveal.html` is genuinely reusable (parameterized, no `/setup`-specific literal
  copy) ahead of `SETUP-012`'s expected reuse next sprint.
- Live-verifies against the real, Compose-run `dashboard-web`/`gateway-api` (per `SETUP-030`) the full
  flow: fresh stack → `/` redirects to `/setup` → submit → key shown → `/login` succeeds with that key.
- Re-runs the full unit + e2e suite, confirms zero regressions.

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md` gains a "Setup wizard (SETUP-003)" section describing the new
  routes, the positioning constraint, and the one-time-reveal partial's intended reuse by `SETUP-012`.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-003` entry's acceptance-criteria
  boxes are checked and its status marked done.
