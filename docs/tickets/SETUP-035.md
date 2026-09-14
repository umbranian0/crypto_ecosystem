# SETUP-035 — `gateway-api`/`dashboard-web`: reject an invalid operator token at login time, not on first use

**Sprint**: 37. **Module**: `services/dashboard-web` (consumer only — no `services/gateway-api`
code change; `GET /tenants`, `SETUP-011`, already exists and is already operator-gated).
**Status**: done (implemented, tests pass, docs updated). **Priority**: Should. **Depends on**: `SETUP-034` (same file/route —
`operator.py`'s `POST /operator-login` handler and `operator_login.html`; sequenced strictly after
per `docs/sprints/sprint-37.md`'s file-overlap note; do not start until `SETUP-034` is
Tech-Lead-verified).

## Analysis

Covers `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-035` story. Today,
`POST /operator-login` (`DASH-113`) accepts any non-empty token, unvalidated, and only fails later
on the first `/settings/*` call — a confusing-UX gap (not a security gap: the token is already
fully enforced downstream by `get_authenticated_operator`, `GW-021`, on every real `/settings/*`
call). This ticket adds one lazy-validation call at login time, the same pattern `DASH-002`
established for tenant login (`POST /login` calling `GET /runs/{uuid}` to detect a `401`).

## Design

**Pattern**: none of implementation-plan.md section 7's patterns apply — this extends an existing
DI-based handler with one more outbound call, no new pattern introduced.

**Files touched** (scoped to `services/dashboard-web/src/app/`):
- `src/app/routers/operator.py` — `operator_login_submit` gains one lazy-validation call to
  gateway-api's `GET /tenants` (`SETUP-011`, already operator-gated via `get_authenticated_operator`)
  using the submitted token as `X-Operator-Token`, via `GatewayApiUrlDep`/a short-lived
  `httpx.Client` (same shape `_call_downstream`/`runs.py` already uses elsewhere in this service —
  reused, not reinvented) with `DOWNSTREAM_HTTP_TIMEOUT_SECONDS`.
- `src/app/templates/operator_login.html` — no structural change expected (the existing `{% if
  error %}` block already renders whatever `error` string the handler passes); update only if a
  distinct copy string is needed.

**Response handling** (binding, per backlog AC and sprint-37.md):
- `response.status_code in (401, 403)` → invalid-token error, redisplay the form (`422`). Both
  codes mean "this value did not authenticate as the operator" per `get_authenticated_operator`'s
  own two rejection branches (`GW-021`/`SETUP-010`: `401` for missing/unknown/revoked, `403` for a
  real-but-wrong-kind tenant key) — both are a real rejection from the operator's point of view,
  so both redisplay the same "invalid operator token" error, not two different messages.
  Any other status (e.g. `200`) is treated as valid — no new gateway-api endpoint introduced solely
  for this check, per the backlog AC.
- `httpx.ConnectError`/`httpx.TimeoutException` → generic "gateway-api is unreachable" error,
  `502`, matching `DASH-002`'s own transport-failure convention exactly — never treated as valid.

**DRY check note**: grepped `src/app/routers/auth.py`'s `login_submit` (`DASH-002`) before writing
this ticket — its `try: client.get(...) except (httpx.ConnectError, httpx.TimeoutException):`
shape plus its `_UNREACHABLE_ERROR`/`_INVALID_KEY_ERROR` constant-string convention is the direct
template for this handler's new validation call; no second lazy-validation pattern invented.
Reuses `GatewayApiUrlDep`/`DOWNSTREAM_HTTP_TIMEOUT_SECONDS` (`dependencies/http_client.py`,
`dependencies/downstream.py`), the same constants every other outbound call in `operator.py`
already imports — not a bare `httpx.get(...)` with an implicit default timeout (the `DASH-121`
timeout-constant rule, `http_client.py`'s own docstring, applies to this new call too).

## Implementation acceptance criteria

- [x] `POST /operator-login` calls `GET /tenants` with the submitted token as `X-Operator-Token`
  before creating a session.
- [x] `401` or `403` response → form redisplays with a clear "Invalid operator token." error,
  `422`, no session created, no cookie set.
- [x] Transport failure (`ConnectError`/`TimeoutException`) → form redisplays with a generic
  "gateway-api is unreachable. Please try again shortly." error, `502`, no session created — never
  treated as valid.
- [x] Any other response status → session created exactly as before (unchanged happy path).
- [x] No new `services/gateway-api` endpoint introduced.
- [x] Positioning check: no new copy implies trading/prediction capability.

## Test acceptance criteria

- [x] New test: submitting a token that gets a `401` from `GET /tenants` (mocked
  `httpx.MockTransport`, same pattern `test_auth.py`'s equivalent `DASH-002` test uses) redisplays
  the form with the invalid-token error, no cookie set.
- [x] New test: a `403` response is treated identically to `401` (invalid, redisplay).
- [x] New test: a transport failure (`ConnectError`) redisplays with the unreachable error, `502`,
  no cookie set.
- [x] Existing happy-path test (`200`/valid token → session cookie set, redirect to `/monitoring`)
  still passes, updated only to mock the new outbound call as a success.
- [x] Full existing dashboard-web suite re-run with zero regressions.

## Review acceptance criteria (Tech Lead verifies personally)

- Confirms the validation call reuses `GatewayApiUrlDep`/`DOWNSTREAM_HTTP_TIMEOUT_SECONDS` — no
  bare `httpx.get()` with a default timeout, matching `DASH-121`'s standing rule.
- Confirms both `401` and `403` are treated as invalid (not just `401`), per the backlog AC's
  explicit two-code list.
- Confirms transport failure is never conflated with "valid" (the single highest-stakes review
  item per `DASH-002`'s own precedent — a false-accept on an unreachable gateway-api would be
  worse than the pre-existing unvalidated-accept behavior).
- Confirms `SETUP-034`'s nav/logout work is untouched by this ticket's diff (file-overlap
  sequencing check).
- Confirms `services/dashboard-web/README.md`'s `DASH-113` "Known gaps" entry for the
  unvalidated-token behavior is removed/updated, not left stale.

## Documentation acceptance criteria

- [x] `services/dashboard-web/README.md`: "Known gaps" entry for `DASH-113`'s unvalidated-token
  behavior removed/updated to state the token is now validated at login time via `GET /tenants`,
  cross-referencing this ticket; add a short "Operator login token validation (SETUP-035)" note
  describing the `401`/`403`-both-invalid design decision.
- [x] `docs/product/backlog-first-run-setup-and-ops.md`'s `SETUP-035` acceptance-criteria boxes
  checked, status marked done, pointer to this ticket.
- [x] `docs/tickets/README.md` gains a Sprint 37 entry for this ticket.
